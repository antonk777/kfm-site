#!/usr/bin/env python3
"""KF-Maniacs secret statistics API + /statistics/ charts.

Uses the same MariaDB as perkhost (kfmaniacs). Tables:
  site_map_sessions      — one row per map play
  site_session_players   — players linked to a map session
  site_daily_snapshot    — peak/unique by day

Listens on 127.0.0.1:STATS_PORT (default 8765) for both HTTP and UDP.
Caddy reverse-proxies /statistics* and /api/stats*. Game sends UDP form bodies
(UE2 TcpLink HTTP was dropping sessions on leave/map travel).

Env (merge /etc/kfm-site.env + /home/kfserver/.kfm-save.env):
  KFM_MYSQL_*   same as perkhost
  STATS_HOST / STATS_PORT / STATS_DAYS
  SITE_LOG      Caddy JSON access log (Companion download counts)
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlparse

HOST = os.environ.get("STATS_HOST", "127.0.0.1")
PORT = int(os.environ.get("STATS_PORT", "8765"))
DAYS = max(30, int(os.environ.get("STATS_DAYS", "180")))
HTML_PATH = Path(__file__).with_name("statistics.html")
LOCK = threading.Lock()
DOWNLOAD_PATH_RE = re.compile(r"^/(download|KFM-Companion[^/]*\.exe)$", re.I)
# Difficulty slots from start.sh — always shown as tabs even with zero rows yet.
KNOWN_SERVERS = ("normal", "hard", "suicidal", "hoe")
# Legacy short name from before per-slot StatsServerName — drop from UI and aggregates.
IGNORED_SERVERS = frozenset({"beta"})
# Game UDP + query UDP (game+1) per slot — used for per-process net counters.
SLOT_PORTS: dict[str, tuple[int, int]] = {
    "normal": (7707, 7708),
    "hard": (7717, 7718),
    "suicidal": (7727, 7728),
    "hoe": (7737, 7738),
}
PID_DIR = Path(os.environ.get("KFM_PID_DIR", "/home/kfserver/run"))
_DOWNLOAD_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_DOWNLOAD_CACHE_TTL = 60.0
LOAD_INTERVAL_SEC = 2.0
LOAD_KEEP = 300  # 10 minutes at 2s
_LOAD_LOCK = threading.Lock()
_LOAD_SAMPLES: list[dict[str, Any]] = []
_LOAD_PREV: dict[str, Any] = {}
_PROC_SAMPLES: dict[str, list[dict[str, Any]]] = {s: [] for s in KNOWN_SERVERS}
_PROC_PREV: dict[str, dict[str, Any]] = {}
_ACCT_READY = False
_ACCT_JUMP_CHECK_TS = 0.0
_LIVE_LOCK = threading.Lock()
# server_name -> latest live snapshot from mutator (or DB fallback)
_LIVE: dict[str, dict[str, Any]] = {}
# Per-slot tick history from live pushes (rolling peak window).
_TICK_SAMPLES: dict[str, list[dict[str, Any]]] = {s: [] for s in KNOWN_SERVERS}
LIVE_STALE_SEC = 45.0
# Peak health / badge uses last N seconds; keep enough history for the load chart too.
TICK_PEAK_WINDOW_SEC = 300  # 5 minutes
TICK_KEEP_SEC = TICK_PEAK_WINDOW_SEC + int(LOAD_INTERVAL_SEC * LOAD_KEEP) + 30


def _read_proc_stat() -> tuple[int, int]:
    """Return (idle+iowait, total) jiffies from /proc/stat."""
    with open("/proc/stat", encoding="utf-8") as fh:
        parts = fh.readline().split()
    # cpu user nice system idle iowait irq softirq steal ...
    nums = [int(x) for x in parts[1:]]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    return idle, total


def _read_meminfo() -> tuple[int, float]:
    """Return (MemTotal_kB, used_pct)."""
    info: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            info[k.strip()] = int(v.strip().split()[0])
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    if total <= 0:
        return 0, 0.0
    used = max(0, total - avail)
    return total, round(100.0 * used / total, 2)


def _read_mem_pct() -> float:
    return _read_meminfo()[1]


def _read_net_bytes() -> int:
    """Sum rx+tx bytes across non-loopback interfaces."""
    total = 0
    with open("/proc/net/dev", encoding="utf-8") as fh:
        lines = fh.readlines()[2:]
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name == "lo" or name.startswith("docker") or name.startswith("veth"):
            continue
        cols = rest.split()
        if len(cols) < 9:
            continue
        total += int(cols[0]) + int(cols[8])
    return total


def _iptables(*args: str) -> tuple[int, str]:
    import subprocess

    try:
        proc = subprocess.run(
            ["iptables", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _ensure_port_accounting() -> bool:
    """Idempotent UDP byte counters per game/query port (INPUT+OUTPUT)."""
    global _ACCT_READY, _ACCT_JUMP_CHECK_TS
    now = time.time()
    if _ACCT_READY and (now - _ACCT_JUMP_CHECK_TS) < 15.0:
        return True
    _ACCT_JUMP_CHECK_TS = now
    rc, _ = _iptables("-L", "KFM_ACCT_IN", "-n")
    if rc != 0:
        for chain in ("KFM_ACCT_IN", "KFM_ACCT_OUT"):
            _iptables("-N", chain)
            _iptables("-F", chain)
        for _slot, ports in SLOT_PORTS.items():
            for port in ports:
                _iptables(
                    "-A", "KFM_ACCT_IN", "-p", "udp", "--dport", str(port), "-j", "RETURN"
                )
                _iptables(
                    "-A", "KFM_ACCT_OUT", "-p", "udp", "--sport", str(port), "-j", "RETURN"
                )
        print("kfm-stats: created UDP port accounting chains", flush=True)
    # Firewall reloads drop jumps but leave chains — re-attach if missing.
    rc, out = _iptables("-L", "INPUT", "-n")
    if rc == 0 and "KFM_ACCT_IN" not in out:
        _iptables("-I", "INPUT", "1", "-j", "KFM_ACCT_IN")
        print("kfm-stats: attached KFM_ACCT_IN -> INPUT", flush=True)
    rc, out = _iptables("-L", "OUTPUT", "-n")
    if rc == 0 and "KFM_ACCT_OUT" not in out:
        _iptables("-I", "OUTPUT", "1", "-j", "KFM_ACCT_OUT")
        print("kfm-stats: attached KFM_ACCT_OUT -> OUTPUT", flush=True)
    rc, _ = _iptables("-L", "KFM_ACCT_IN", "-n", "-v", "-x")
    _ACCT_READY = rc == 0
    return _ACCT_READY


def _read_port_bytes(chain: str) -> dict[int, int]:
    """Map udp port → cumulative bytes from KFM_ACCT_* RETURN rules."""
    rc, out = _iptables("-L", chain, "-n", "-v", "-x")
    if rc != 0:
        return {}
    by_port: dict[int, int] = {}
    for line in out.splitlines():
        # e.g. "    12  3456 RETURN ... udp dpt:7707"
        if "RETURN" not in line or "udp" not in line:
            continue
        cols = line.split()
        if len(cols) < 2:
            continue
        try:
            nbytes = int(cols[1])
        except ValueError:
            continue
        port = None
        for tok in cols:
            if tok.startswith("dpt:") or tok.startswith("spt:"):
                try:
                    port = int(tok.split(":", 1)[1])
                except ValueError:
                    port = None
                break
        if port is not None:
            by_port[port] = by_port.get(port, 0) + nbytes
    return by_port


def _slot_net_bytes() -> dict[str, int]:
    """rx+tx UDP bytes per slot from iptables accounting."""
    if not _ensure_port_accounting():
        return {}
    inn = _read_port_bytes("KFM_ACCT_IN")
    out = _read_port_bytes("KFM_ACCT_OUT")
    result: dict[str, int] = {}
    for slot, ports in SLOT_PORTS.items():
        total = 0
        for port in ports:
            total += int(inn.get(port, 0)) + int(out.get(port, 0))
        result[slot] = total
    return result


def _resolve_slot_pid(slot: str) -> int | None:
    """PID from run/<slot>.pid, verified alive and matching -port=."""
    path = PID_DIR / f"{slot}.pid"
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid <= 1 or not Path(f"/proc/{pid}").is_dir():
        return None
    ports = SLOT_PORTS.get(slot)
    if not ports:
        return pid
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        )
    except OSError:
        return None
    want = f"-port={ports[0]}"
    if want not in cmdline and f"port={ports[0]}" not in cmdline:
        # Still accept if it's clearly ucc for this slot's System dir.
        if "ucc-bin" not in cmdline:
            return None
    return pid


def _read_pid_cpu_jiffies(pid: int) -> int | None:
    try:
        parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        # utime=14 stime=15 (1-based) → indices 13,14
        return int(parts[13]) + int(parts[14])
    except (OSError, IndexError, ValueError):
        return None


def _read_pid_rss_kb(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _sample_host_load() -> dict[str, Any] | None:
    """One host sample; needs a previous sample for CPU/net rates."""
    global _LOAD_PREV
    try:
        idle, total = _read_proc_stat()
        mem = _read_mem_pct()
        net_b = _read_net_bytes()
        now = time.time()
    except OSError:
        return None

    prev = _LOAD_PREV
    _LOAD_PREV = {"idle": idle, "total": total, "net": net_b, "ts": now}
    if not prev:
        return None

    d_total = total - int(prev["total"])
    d_idle = idle - int(prev["idle"])
    if d_total <= 0:
        cpu = 0.0
    else:
        cpu = max(0.0, min(100.0, round(100.0 * (1.0 - d_idle / d_total), 2)))

    dt = max(0.001, now - float(prev["ts"]))
    d_net = max(0, net_b - int(prev["net"]))
    net_mbps = round((d_net * 8.0) / dt / 1_000_000.0, 3)

    return {
        "ts": int(now),
        "cpu": cpu,
        "mem": mem,
        "net_mbps": net_mbps,
        "scope": "host",
    }


def _sample_slot_load(now: float, host_total: int, mem_total_kb: int) -> None:
    """Append one sample per known slot (process CPU/RSS + UDP port Mbps)."""
    net_by_slot = _slot_net_bytes()
    for slot in KNOWN_SERVERS:
        pid = _resolve_slot_pid(slot)
        proc_j = _read_pid_cpu_jiffies(pid) if pid else None
        rss_kb = _read_pid_rss_kb(pid) if pid else None
        net_b = int(net_by_slot.get(slot, 0))
        prev = _PROC_PREV.get(slot)
        _PROC_PREV[slot] = {
            "pid": pid,
            "jiffies": proc_j,
            "host_total": host_total,
            "net": net_b,
            "ts": now,
        }
        if not prev or proc_j is None or rss_kb is None or prev.get("jiffies") is None:
            continue
        if prev.get("pid") != pid:
            continue
        d_proc = proc_j - int(prev["jiffies"])
        d_host = host_total - int(prev["host_total"])
        if d_host <= 0 or d_proc < 0:
            cpu = 0.0
        else:
            cpu = max(0.0, min(100.0, round(100.0 * d_proc / d_host, 2)))
        mem_pct = (
            round(100.0 * rss_kb / mem_total_kb, 2) if mem_total_kb > 0 else 0.0
        )
        mem_mb = round(rss_kb / 1024.0, 1)
        dt = max(0.001, now - float(prev["ts"]))
        d_net = max(0, net_b - int(prev["net"]))
        net_mbps = round((d_net * 8.0) / dt / 1_000_000.0, 3)
        sample = {
            "ts": int(now),
            "cpu": cpu,
            "mem": mem_pct,
            "mem_mb": mem_mb,
            "net_mbps": net_mbps,
            "pid": pid,
            "scope": "process",
            "server": slot,
        }
        with _LOAD_LOCK:
            buf = _PROC_SAMPLES.setdefault(slot, [])
            buf.append(sample)
            if len(buf) > LOAD_KEEP:
                del buf[: len(buf) - LOAD_KEEP]


def load_sampler_loop() -> None:
    _ensure_port_accounting()
    while True:
        sample = _sample_host_load()
        if sample is not None:
            with _LOAD_LOCK:
                _LOAD_SAMPLES.append(sample)
                if len(_LOAD_SAMPLES) > LOAD_KEEP:
                    del _LOAD_SAMPLES[: len(_LOAD_SAMPLES) - LOAD_KEEP]
        try:
            _, total = _read_proc_stat()
            mem_total_kb, _ = _read_meminfo()
            _sample_slot_load(time.time(), total, mem_total_kb)
        except OSError:
            pass
        time.sleep(LOAD_INTERVAL_SEC)


def build_load_series(server: str | None = None) -> dict[str, Any]:
    with _LOAD_LOCK:
        if server and server in _PROC_SAMPLES:
            samples = list(_PROC_SAMPLES.get(server) or [])
            scope = "process"
        else:
            samples = list(_LOAD_SAMPLES)
            scope = "host"
            server = None
    now = samples[-1] if samples else None
    out: dict[str, Any] = {
        "interval_sec": LOAD_INTERVAL_SEC,
        "scope": scope,
        "server": server or "",
        "ts": [s["ts"] for s in samples],
        "cpu": [s["cpu"] for s in samples],
        "mem": [s["mem"] for s in samples],
        "mem_mb": [s.get("mem_mb") for s in samples],
        "net_mbps": [s["net_mbps"] for s in samples],
        "now": now,
        "tick_ms": [],
        "peak_tick_ms": [],
        "peakTick": -1,
        "peakWindowSec": TICK_PEAK_WINDOW_SEC,
    }
    if server:
        with _LIVE_LOCK:
            ticks = list(_TICK_SAMPLES.get(server) or [])
        # Forward-fill window tick + rolling 5-min peak onto load sample timestamps.
        tick_ms: list[float | None] = []
        peak_ms: list[float | None] = []
        ti = 0
        last: float | None = None
        lo = 0
        win_max = -1
        # Multiset of ms in [ts - window, ts] via two pointers (ticks sorted by ts).
        win: deque[int] = deque()
        for ts in out["ts"]:
            tsi = int(ts)
            while ti < len(ticks) and int(ticks[ti]["ts"]) <= tsi:
                ms = int(ticks[ti]["ms"])
                last = float(ms)
                win.append(ms)
                if ms >= win_max:
                    win_max = ms
                ti += 1
            cutoff = tsi - TICK_PEAK_WINDOW_SEC
            while lo < ti and int(ticks[lo]["ts"]) < cutoff:
                dropped = win.popleft()
                lo += 1
                if dropped == win_max:
                    win_max = max(win) if win else -1
            tick_ms.append(last)
            peak_ms.append(float(win_max) if win_max >= 0 else None)
        out["tick_ms"] = tick_ms
        out["peak_tick_ms"] = peak_ms
        out["tick_ts"] = [int(t["ts"]) for t in ticks]
        out["tick_raw"] = [int(t["ms"]) for t in ticks]
        out["peakTick"] = _peak_tick_from_samples(ticks)
        out["live"] = get_live_status(server)
    # Always include all slots so tab traffic-lights stay current.
    out["liveAll"] = {s: get_live_status(s) for s in KNOWN_SERVERS}
    return out


def _prune_tick_buf(buf: list[dict[str, Any]], now: int | float) -> None:
    cutoff = int(now) - TICK_KEEP_SEC
    while buf and int(buf[0]["ts"]) < cutoff:
        del buf[0]


def _peak_tick_from_samples(
    ticks: list[dict[str, Any]],
    *,
    now: int | float | None = None,
    window_sec: int = TICK_PEAK_WINDOW_SEC,
) -> int:
    if not ticks:
        return -1
    t_now = int(now if now is not None else now_ts())
    cutoff = t_now - int(window_sec)
    peak = -1
    for t in ticks:
        if int(t["ts"]) < cutoff:
            continue
        ms = int(t["ms"])
        if ms > peak:
            peak = ms
    return peak


def _peak_tick_for(server: str) -> int:
    with _LIVE_LOCK:
        return _peak_tick_from_samples(list(_TICK_SAMPLES.get(server) or []))


def _parse_live_players(raw: str) -> list[dict[str, Any]]:
    """players=name|perkIdx|perk|steam,name2|..."""
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        name = unquote_plus(parts[0]) if parts else ""
        perk_idx = -1
        perk = ""
        steam = ""
        if len(parts) > 1:
            try:
                perk_idx = int(parts[1])
            except ValueError:
                perk_idx = -1
        if len(parts) > 2:
            perk = unquote_plus(parts[2])
        if len(parts) > 3:
            steam = unquote_plus(parts[3])
        out.append(
            {
                "name": name[:64],
                "perk": perk[:32],
                "perkIdx": perk_idx,
                "steam": steam[:64],
            }
        )
    return out


def ingest_live(_con, p: dict[str, Any]) -> None:
    server = str(p.get("server") or p.get("server_name") or "").strip().lower()[:64]
    if not server or server in IGNORED_SERVERS:
        return
    players = _parse_live_players(str(p.get("players") or ""))
    online = int(num(p.get("online"), len(players)))
    map_name = str(p.get("map") or p.get("map_name") or "")[:64]
    tick_ms = int(num(p.get("worstTick"), -1))
    ts = now_ts()
    snap = {
        "server": server,
        "map": map_name,
        "wave": int(num(p.get("wave"), 0)),
        "finalWave": int(num(p.get("finalWave"), num(p.get("final_wave"), 0))),
        "online": online,
        "players": players,
        "worstTick": tick_ms,
        "ts": ts,
        "source": "live",
    }
    with _LIVE_LOCK:
        if tick_ms >= 0:
            buf = _TICK_SAMPLES.setdefault(server, [])
            buf.append({"ts": ts, "ms": tick_ms})
            _prune_tick_buf(buf, ts)
        peak = _peak_tick_from_samples(_TICK_SAMPLES.get(server) or [], now=ts)
        snap["peakTick"] = peak
        snap["peakWindowSec"] = TICK_PEAK_WINDOW_SEC
        _LIVE[server] = snap


def _live_from_db(con, server: str) -> dict[str, Any] | None:
    """Fallback from open map session (may be stale until mutator live push)."""
    cur = con.cursor()
    cur.execute(
        """
        SELECT `id`, `map_name`, `wave`, `final_wave`, `player_count`, `started_at`
        FROM `site_map_sessions`
        WHERE `server_name`=%s AND `ended_at`=0 AND `player_count`>0
        ORDER BY `started_at` DESC LIMIT 1
        """,
        (server,),
    )
    row = cur.fetchone()
    if not row:
        return None
    # Ignore shells older than 3h without updates.
    if now_ts() - int(row["started_at"] or 0) > 3 * 3600:
        return None
    cur.execute(
        """
        SELECT `name`, `perk_name` AS perk, `perk_index` AS perkIdx, `steam_id` AS steam
        FROM `site_session_players`
        WHERE `session_id`=%s AND `left_at`=0
        ORDER BY `joined_at`
        """,
        (int(row["id"]),),
    )
    players = [
        {
            "name": str(r["name"] or "")[:64],
            "perk": str(r["perk"] or "")[:32],
            "perkIdx": int(r["perkIdx"] if r["perkIdx"] is not None else -1),
            "steam": str(r["steam"] or "")[:64],
        }
        for r in cur.fetchall()
    ]
    return {
        "server": server,
        "map": str(row["map_name"] or "")[:64],
        "wave": int(row["wave"] or 0),
        "finalWave": int(row["final_wave"] or 0),
        "online": max(int(row["player_count"] or 0), len(players)),
        "players": players,
        "worstTick": -1,
        "ts": int(row["started_at"] or 0),
        "source": "db",
    }


# Tick health thresholds (ms). Current window + 5-min peak drive the light.
TICK_OK_MS = 50
TICK_WARN_MS = 100
TICK_BAD_MS = 250


def tick_health(
    tick_ms: int | float | None,
    peak_ms: int | float | None = -1,
    *,
    stale: bool = False,
) -> dict[str, Any]:
    """Traffic-light health from tick latency (current + 5-min peak)."""
    try:
        t = int(tick_ms) if tick_ms is not None else -1
    except (TypeError, ValueError):
        t = -1
    try:
        pk = int(peak_ms) if peak_ms is not None else -1
    except (TypeError, ValueError):
        pk = -1
    if stale or (t < 0 and pk < 0):
        return {
            "level": "unknown",
            "label": "Нет данных",
            "tickMs": t if t >= 0 else None,
            "peakMs": pk if pk >= 0 else None,
            "peakWindowSec": TICK_PEAK_WINDOW_SEC,
        }
    # Score by the worse of current window and recent peak.
    score = max(t, pk)
    if score >= TICK_BAD_MS:
        level, label = "bad", "Плохо"
    elif score >= TICK_WARN_MS:
        level, label = "warn", "Средне"
    elif score >= TICK_OK_MS:
        level, label = "ok", "Норма"
    else:
        level, label = "good", "Отлично"
    return {
        "level": level,
        "label": label,
        "tickMs": t if t >= 0 else None,
        "peakMs": pk if pk >= 0 else None,
        "peakWindowSec": TICK_PEAK_WINDOW_SEC,
    }


def _attach_health(snap: dict[str, Any]) -> dict[str, Any]:
    snap = dict(snap)
    peak = snap.get("peakTick", -1)
    if peak is None or int(peak) < 0:
        peak = snap.get("worstTick", -1)
    snap["peakTick"] = int(peak) if peak is not None and int(peak) >= 0 else -1
    snap["peakWindowSec"] = TICK_PEAK_WINDOW_SEC
    snap["health"] = tick_health(
        snap.get("worstTick"),
        snap["peakTick"],
        stale=bool(snap.get("stale")),
    )
    return snap


def get_live_status(server: str) -> dict[str, Any]:
    empty = {
        "server": server,
        "map": "",
        "wave": 0,
        "finalWave": 0,
        "online": 0,
        "players": [],
        "worstTick": -1,
        "peakTick": -1,
        "peakWindowSec": TICK_PEAK_WINDOW_SEC,
        "ts": 0,
        "source": "none",
        "stale": True,
    }
    with _LIVE_LOCK:
        snap = dict(_LIVE.get(server) or {})
        ticks = list(_TICK_SAMPLES.get(server) or [])
    peak = _peak_tick_from_samples(ticks)
    if snap:
        age = now_ts() - int(snap.get("ts") or 0)
        snap["stale"] = age > LIVE_STALE_SEC
        snap["peakTick"] = peak
        snap["peakWindowSec"] = TICK_PEAK_WINDOW_SEC
        if not snap["stale"]:
            return _attach_health(snap)
    # Fall back to DB if live push missing/stale (needs Handler.con).
    con = getattr(Handler, "con", None)
    if con is not None:
        try:
            with LOCK:
                db = _live_from_db(con, server)
            if db:
                db["stale"] = True
                db["peakTick"] = peak
                db["peakWindowSec"] = TICK_PEAK_WINDOW_SEC
                return _attach_health(db)
        except Exception:  # noqa: BLE001
            pass
    if snap:
        return _attach_health(snap)
    empty["peakTick"] = peak
    return _attach_health(empty)


def mysql_cfg() -> dict[str, Any]:
    return {
        "host": os.environ.get("KFM_MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1",
        "port": int(os.environ.get("KFM_MYSQL_PORT", "3306") or "3306"),
        "user": os.environ.get("KFM_MYSQL_USER", "kfm").strip() or "kfm",
        "password": os.environ.get("KFM_MYSQL_PASSWORD", ""),
        "db": os.environ.get("KFM_MYSQL_DB", "kfmaniacs").strip() or "kfmaniacs",
    }


def connect():
    import pymysql

    cfg = mysql_cfg()
    if not cfg["password"]:
        raise RuntimeError("KFM_MYSQL_PASSWORD empty — load /home/kfserver/.kfm-save.env")
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["db"],
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_schema(con) -> None:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS `site_map_sessions` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `session_key` VARCHAR(128) NOT NULL,
          `map_name` VARCHAR(64) NOT NULL DEFAULT '',
          `started_at` INT NOT NULL,
          `ended_at` INT NOT NULL DEFAULT 0,
          `duration_sec` INT NOT NULL DEFAULT 0,
          `outcome` VARCHAR(16) NOT NULL DEFAULT 'unknown',
          `wave` INT NOT NULL DEFAULT 0,
          `final_wave` INT NOT NULL DEFAULT 0,
          `difficulty` DOUBLE NOT NULL DEFAULT 0,
          `day` INT NOT NULL,
          `server_name` VARCHAR(64) NOT NULL DEFAULT '',
          `player_count` INT NOT NULL DEFAULT 0,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_site_map_key` (`session_key`),
          KEY `idx_site_map_day` (`day`),
          KEY `idx_site_map_name` (`map_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS `site_session_players` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `session_id` BIGINT NOT NULL,
          `session_key` VARCHAR(128) NOT NULL,
          `steam_id` VARCHAR(64) NOT NULL,
          `name` VARCHAR(64) NOT NULL DEFAULT '',
          `joined_at` INT NOT NULL DEFAULT 0,
          `left_at` INT NOT NULL DEFAULT 0,
          `duration_sec` INT NOT NULL DEFAULT 0,
          `perk_index` INT NOT NULL DEFAULT -1,
          `perk_name` VARCHAR(32) NOT NULL DEFAULT '',
          `max_wave` INT NOT NULL DEFAULT 0,
          `outcome` VARCHAR(16) NOT NULL DEFAULT 'unknown',
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_site_sess_player` (`session_key`, `steam_id`),
          KEY `idx_site_sp_session` (`session_id`),
          KEY `idx_site_sp_steam` (`steam_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS `site_daily_snapshot` (
          `day` INT NOT NULL,
          `server_name` VARCHAR(64) NOT NULL DEFAULT '',
          `peak` INT NOT NULL DEFAULT 0,
          `unique_count` INT NOT NULL DEFAULT 0,
          `updated_at` INT NOT NULL,
          PRIMARY KEY (`day`, `server_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    # Migrate pre-per-server snapshot table (PK was day only).
    cur.execute("SHOW COLUMNS FROM `site_daily_snapshot` LIKE 'server_name'")
    if not cur.fetchone():
        cur.execute(
            """
            ALTER TABLE `site_daily_snapshot`
              ADD COLUMN `server_name` VARCHAR(64) NOT NULL DEFAULT '' AFTER `day`
            """
        )
        cur.execute("ALTER TABLE `site_daily_snapshot` DROP PRIMARY KEY")
        cur.execute(
            "ALTER TABLE `site_daily_snapshot` ADD PRIMARY KEY (`day`, `server_name`)"
        )
        print("kfm-stats: migrated site_daily_snapshot +server_name", flush=True)
    # Drop lobby shells that never got a human player.
    cur.execute(
        """
        DELETE sp FROM `site_session_players` sp
        INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
        WHERE ms.`player_count`<=0
        """
    )
    cur.execute("DELETE FROM `site_map_sessions` WHERE `player_count`<=0")
    if cur.rowcount:
        print(f"kfm-stats: purged {cur.rowcount} empty map sessions", flush=True)


def now_ts() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def day_from_ts(ts: int) -> int:
    d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return d.year * 10000 + d.month * 100 + d.day


def parse_day(n: int) -> date:
    y, m, d = n // 10000, (n % 10000) // 100, n % 100
    return date(y, m, d)


def add_days(yyyymmdd: int, n: int) -> int:
    d = parse_day(yyyymmdd) + timedelta(days=n)
    return d.year * 10000 + d.month * 100 + d.day


def num(v: Any, default: float | int = 0) -> float | int:
    try:
        if v is None or v == "":
            return default
        if isinstance(default, int):
            return int(float(v))
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_body(raw: bytes, ctype: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "application/json" in (ctype or "").lower():
        try:
            data = json.loads(text or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    out: dict[str, Any] = {}
    for part in text.split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        out[unquote_plus(k)] = unquote_plus(v)
    return out


def touch_player(con, steam: str, name: str) -> None:
    """Best-effort update of perkhost `players` row; never invent accounts."""
    cur = con.cursor()
    if name:
        cur.execute(
            """
            UPDATE `players`
            SET `last_player_name`=%s, `last_time_joined`=NOW()
            WHERE `steam_id`=%s
            """,
            (name[:64], steam),
        )
    else:
        cur.execute(
            "UPDATE `players` SET `last_time_joined`=NOW() WHERE `steam_id`=%s",
            (steam,),
        )


def ensure_map_session(con, p: dict[str, Any]) -> int:
    """Insert/update map session by session_key; return session id."""
    key = str(p.get("key") or p.get("session_key") or "").strip()
    if not key:
        raise ValueError("session key required")
    map_name = str(p.get("map") or p.get("map_name") or "")[:64]
    started = int(num(p.get("started_at"), now_ts()))
    day = int(num(p.get("day"), day_from_ts(started)))
    difficulty = float(num(p.get("diff"), num(p.get("difficulty"), 0.0)))
    server_name = str(p.get("server") or p.get("server_name") or "")[:64]
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO `site_map_sessions`(
          `session_key`, `map_name`, `started_at`, `day`, `difficulty`, `server_name`
        ) VALUES(%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          `map_name`=IF(VALUES(`map_name`)='', `map_name`, VALUES(`map_name`)),
          `difficulty`=IF(VALUES(`difficulty`)=0, `difficulty`, VALUES(`difficulty`)),
          `server_name`=IF(VALUES(`server_name`)='', `server_name`, VALUES(`server_name`))
        """,
        (key, map_name, started, day, difficulty, server_name),
    )
    cur.execute("SELECT `id` FROM `site_map_sessions` WHERE `session_key`=%s", (key,))
    row = cur.fetchone()
    if not row:
        raise ValueError("map session missing after upsert")
    return int(row["id"])


def ingest_map_open(con, p: dict[str, Any]) -> None:
    with LOCK:
        ensure_map_session(con, p)


def ingest_map_close(con, p: dict[str, Any]) -> None:
    key = str(p.get("key") or p.get("session_key") or "").strip()
    if not key:
        raise ValueError("session key required")
    ended = int(num(p.get("ended_at"), now_ts()))
    duration = max(0, int(num(p.get("duration"), num(p.get("duration_sec"), 0))))
    outcome = str(p.get("outcome") or "unknown").lower()[:16]
    wave = int(num(p.get("wave"), 0))
    final_wave = int(num(p.get("finalWave"), num(p.get("final_wave"), 0)))
    difficulty = float(num(p.get("diff"), num(p.get("difficulty"), 0.0)))
    day = int(num(p.get("day"), day_from_ts(ended)))
    with LOCK:
        sid = ensure_map_session(con, p)
        cur = con.cursor()
        cur.execute(
            """
            UPDATE `site_map_sessions` SET
              `ended_at`=GREATEST(`ended_at`, %s),
              `duration_sec`=GREATEST(`duration_sec`, %s),
              `outcome`=%s,
              `wave`=GREATEST(`wave`, %s),
              `final_wave`=GREATEST(`final_wave`, %s),
              `difficulty`=IF(%s=0, `difficulty`, %s),
              `day`=%s,
              `player_count`=(
                SELECT COUNT(*) FROM `site_session_players` WHERE `session_id`=%s
              )
            WHERE `id`=%s
            """,
            (ended, duration, outcome, wave, final_wave, difficulty, difficulty, day, sid, sid),
        )
        cur.execute(
            "SELECT `player_count` AS c FROM `site_map_sessions` WHERE `id`=%s", (sid,)
        )
        row = cur.fetchone()
        # Lobby / bots-only shells: drop so they never enter charts.
        if row is not None and int(row["c"] or 0) <= 0:
            cur.execute("DELETE FROM `site_session_players` WHERE `session_id`=%s", (sid,))
            cur.execute("DELETE FROM `site_map_sessions` WHERE `id`=%s", (sid,))


def ingest_player_join(con, p: dict[str, Any]) -> None:
    key = str(p.get("key") or p.get("session_key") or "").strip()
    steam = str(p.get("steam") or p.get("steam_id") or "").strip()
    if not key or not steam:
        raise ValueError("key and steam required")
    name = str(p.get("name") or p.get("player") or "")[:64]
    joined = int(num(p.get("joined_at"), now_ts()))
    perk_index = int(num(p.get("perkIdx"), num(p.get("perk_index"), -1)))
    perk_name = str(p.get("perk") or p.get("perk_name") or "")[:32]
    with LOCK:
        sid = ensure_map_session(con, p)
        touch_player(con, steam, name)
        con.cursor().execute(
            """
            INSERT INTO `site_session_players`(
              `session_id`, `session_key`, `steam_id`, `name`, `joined_at`,
              `perk_index`, `perk_name`, `outcome`
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,'joined')
            ON DUPLICATE KEY UPDATE
              `name`=IF(VALUES(`name`)='', `name`, VALUES(`name`)),
              `joined_at`=LEAST(IF(`joined_at`=0, VALUES(`joined_at`), `joined_at`), VALUES(`joined_at`)),
              `perk_index`=IF(VALUES(`perk_name`)='', `perk_index`, VALUES(`perk_index`)),
              `perk_name`=IF(VALUES(`perk_name`)='', `perk_name`, VALUES(`perk_name`)),
              `outcome`=IF(`outcome` IN ('leave','win','loss'), `outcome`, 'joined')
            """,
            (sid, key, steam, name, joined, perk_index, perk_name),
        )
        con.cursor().execute(
            """
            UPDATE `site_map_sessions` SET `player_count`=(
              SELECT COUNT(*) FROM `site_session_players` WHERE `session_id`=%s
            ) WHERE `id`=%s
            """,
            (sid, sid),
        )


def ingest_player_leave(con, p: dict[str, Any]) -> None:
    key = str(p.get("key") or p.get("session_key") or "").strip()
    steam = str(p.get("steam") or p.get("steam_id") or "").strip()
    if not key or not steam:
        raise ValueError("key and steam required")
    name = str(p.get("name") or p.get("player") or "")[:64]
    joined = int(num(p.get("joined_at"), 0))
    left = int(num(p.get("left_at"), now_ts()))
    duration = max(0, int(num(p.get("duration"), num(p.get("duration_sec"), 0))))
    perk_index = int(num(p.get("perkIdx"), num(p.get("perk_index"), -1)))
    perk_name = str(p.get("perk") or p.get("perk_name") or "")[:32]
    outcome = str(p.get("outcome") or "leave").lower()[:16]
    wave = int(num(p.get("wave"), 0))
    with LOCK:
        sid = ensure_map_session(con, p)
        touch_player(con, steam, name)
        con.cursor().execute(
            """
            INSERT INTO `site_session_players`(
              `session_id`, `session_key`, `steam_id`, `name`, `joined_at`, `left_at`,
              `duration_sec`, `perk_index`, `perk_name`, `max_wave`, `outcome`
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              `name`=IF(VALUES(`name`)='', `name`, VALUES(`name`)),
              `joined_at`=IF(`joined_at`=0, VALUES(`joined_at`), LEAST(`joined_at`, VALUES(`joined_at`))),
              `left_at`=GREATEST(`left_at`, VALUES(`left_at`)),
              `duration_sec`=GREATEST(`duration_sec`, VALUES(`duration_sec`)),
              `perk_index`=IF(VALUES(`perk_name`)='', `perk_index`, VALUES(`perk_index`)),
              `perk_name`=IF(VALUES(`perk_name`)='', `perk_name`, VALUES(`perk_name`)),
              `max_wave`=GREATEST(`max_wave`, VALUES(`max_wave`)),
              `outcome`=VALUES(`outcome`)
            """,
            (
                sid,
                key,
                steam,
                name,
                joined,
                left,
                duration,
                perk_index,
                perk_name,
                wave,
                outcome,
            ),
        )
        con.cursor().execute(
            """
            UPDATE `site_map_sessions` SET `player_count`=(
              SELECT COUNT(*) FROM `site_session_players` WHERE `session_id`=%s
            ) WHERE `id`=%s
            """,
            (sid, sid),
        )


def ingest_daily(con, p: dict[str, Any]) -> None:
    day = int(num(p.get("day"), 0))
    if day <= 0:
        raise ValueError("day required")
    server_name = str(p.get("server") or p.get("server_name") or "")[:64]
    if server_name.lower() in IGNORED_SERVERS:
        server_name = ""
    with LOCK:
        con.cursor().execute(
            """
            INSERT INTO `site_daily_snapshot`
              (`day`, `server_name`, `peak`, `unique_count`, `updated_at`)
            VALUES(%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              `peak`=GREATEST(`peak`, VALUES(`peak`)),
              `unique_count`=GREATEST(`unique_count`, VALUES(`unique_count`)),
              `updated_at`=VALUES(`updated_at`)
            """,
            (
                day,
                server_name,
                int(num(p.get("peak"), 0)),
                int(num(p.get("unique"), num(p.get("unique_count"), 0))),
                now_ts(),
            ),
        )


def site_log_path() -> Path:
    return Path(
        os.environ.get("SITE_LOG", "/var/log/caddy/kfm.manul.lol.log").strip()
        or "/var/log/caddy/kfm.manul.lol.log"
    )


def site_log_files(primary: Path) -> list[Path]:
    """Current Caddy log + rolled siblings (name, name.1, name.*.log, …)."""
    if not primary.parent.is_dir():
        return [primary] if primary.is_file() else []
    stem = primary.name
    found: list[Path] = []
    for p in primary.parent.iterdir():
        if not p.is_file():
            continue
        if p.name == stem or p.name.startswith(stem + "."):
            found.append(p)
    found.sort(key=lambda p: (p != primary, p.name))
    return found or ([primary] if primary.is_file() else [])


def _log_uri(row: dict[str, Any]) -> str:
    req = row.get("request") if isinstance(row.get("request"), dict) else {}
    uri = req.get("uri") or req.get("url") or row.get("uri") or row.get("url") or ""
    return str(uri).split("?", 1)[0]


def _log_day(row: dict[str, Any]) -> int | None:
    ts = row.get("ts")
    try:
        if ts is None:
            return None
        return day_from_ts(int(float(ts)))
    except (TypeError, ValueError):
        return None


def parse_download_stats(min_day: int) -> dict[str, Any]:
    """Count Companion downloads from Caddy JSON access logs (cached)."""
    now = time.monotonic()
    cached = _DOWNLOAD_CACHE.get("data")
    if cached is not None and (now - float(_DOWNLOAD_CACHE["ts"])) < _DOWNLOAD_CACHE_TTL:
        return cached

    by_day: dict[int, int] = {}
    by_path: dict[str, int] = {}
    total = 0
    files_read = 0
    for path in site_log_files(site_log_path()):
        if not path.is_file():
            continue
        files_read += 1
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    status = int(row.get("status") or row.get("status_code") or 0)
                    if status < 200 or status >= 400:
                        continue
                    uri = _log_uri(row)
                    if not DOWNLOAD_PATH_RE.match(uri):
                        continue
                    day = _log_day(row)
                    total += 1
                    by_path[uri] = by_path.get(uri, 0) + 1
                    if day is not None and day >= min_day:
                        by_day[day] = by_day.get(day, 0) + 1
        except OSError as exc:
            print(f"download log read skipped {path}: {exc}", flush=True)

    today = day_from_ts(now_ts())
    data = {
        "total": total,
        "today": int(by_day.get(today, 0)),
        "by_day": by_day,
        "by_path": by_path,
        "log": str(site_log_path()),
        "files": files_read,
    }
    _DOWNLOAD_CACHE["ts"] = now
    _DOWNLOAD_CACHE["data"] = data
    return data


def normalize_server(raw: str | None) -> str | None:
    """Empty / all / * → None (aggregate). Otherwise short server id."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in ("all", "все", "*", "any") or s in IGNORED_SERVERS:
        return None
    return s[:64]


def server_sql(server: str | None, col: str = "`server_name`") -> tuple[str, tuple[Any, ...]]:
    if server:
        return f" AND {col}=%s", (server,)
    # «Все»: only live difficulty slots — exclude legacy beta / empty / unknown.
    placeholders = ",".join(["%s"] * len(KNOWN_SERVERS))
    return f" AND {col} IN ({placeholders})", tuple(KNOWN_SERVERS)


def nonempty_session_sql(col: str = "`player_count`") -> str:
    """Exclude lobby shells / bots-only map opens with no human players."""
    return f" AND {col}>0"


def list_servers(con) -> list[dict[str, Any]]:
    """Only the four difficulty slots (no legacy beta)."""
    cur = con.cursor()
    placeholders = ",".join(["%s"] * len(KNOWN_SERVERS))
    cur.execute(
        f"""
        SELECT `server_name` AS name, COUNT(*) AS c
        FROM `site_map_sessions`
        WHERE `server_name` IN ({placeholders}){nonempty_session_sql()}
        GROUP BY `server_name`
        """,
        tuple(KNOWN_SERVERS),
    )
    counts = {str(r["name"]): int(r["c"]) for r in cur.fetchall()}
    return [{"name": name, "c": int(counts.get(name, 0))} for name in KNOWN_SERVERS]


def day_list(
    con,
    min_day: int,
    extra_days: list[int] | None = None,
    server: str | None = None,
) -> list[int]:
    cur = con.cursor()
    srv_sql, srv_args = server_sql(server)
    if server:
        cur.execute(
            f"""
            SELECT DISTINCT `day` FROM (
              SELECT `day` FROM `site_map_sessions`
              WHERE `day` >= %s{srv_sql}{nonempty_session_sql()}
              UNION
              SELECT `day` FROM `site_daily_snapshot`
              WHERE `day` >= %s AND `server_name`=%s
            ) t ORDER BY `day`
            """,
            (min_day, *srv_args, min_day, server),
        )
    else:
        placeholders = ",".join(["%s"] * len(KNOWN_SERVERS))
        cur.execute(
            f"""
            SELECT DISTINCT `day` FROM (
              SELECT `day` FROM `site_map_sessions`
              WHERE `day` >= %s{srv_sql}{nonempty_session_sql()}
              UNION
              SELECT `day` FROM `site_daily_snapshot`
              WHERE `day` >= %s AND (
                `server_name` IN ({placeholders}) OR `server_name`=''
              )
            ) t ORDER BY `day`
            """,
            (min_day, *srv_args, min_day, *KNOWN_SERVERS),
        )
    days = {int(r["day"]) for r in cur.fetchall()}
    if extra_days and not server:
        for d in extra_days:
            if d >= min_day:
                days.add(int(d))
    return sorted(days)


def day_start_ts(yyyymmdd: int) -> int:
    d = parse_day(yyyymmdd)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _snap_peak_unique(con, day: int, server: str | None) -> tuple[int, int]:
    """Peak/unique from site_daily_snapshot for one day (per-server or All)."""
    cur = con.cursor()
    if server:
        cur.execute(
            """
            SELECT `peak`, `unique_count` FROM `site_daily_snapshot`
            WHERE `day`=%s AND `server_name`=%s
            """,
            (day, server),
        )
        row = cur.fetchone()
        if not row:
            return 0, 0
        return int(row["peak"] or 0), int(row["unique_count"] or 0)
    placeholders = ",".join(["%s"] * len(KNOWN_SERVERS))
    cur.execute(
        f"""
        SELECT COALESCE(SUM(`peak`), 0) AS peak,
               COALESCE(SUM(`unique_count`), 0) AS uniq
        FROM `site_daily_snapshot`
        WHERE `day`=%s AND `server_name` IN ({placeholders})
        """,
        (day, *KNOWN_SERVERS),
    )
    named = cur.fetchone() or {}
    peak_named = int(named.get("peak") or 0)
    uniq_named = int(named.get("uniq") or 0)
    cur.execute(
        """
        SELECT `peak`, `unique_count` FROM `site_daily_snapshot`
        WHERE `day`=%s AND `server_name`=''
        """,
        (day,),
    )
    legacy = cur.fetchone()
    if peak_named == 0 and uniq_named == 0 and legacy:
        return int(legacy["peak"] or 0), int(legacy["unique_count"] or 0)
    peak_legacy = int(legacy["peak"] or 0) if legacy else 0
    uniq_legacy = int(legacy["unique_count"] or 0) if legacy else 0
    return max(peak_named, peak_legacy), max(uniq_named, uniq_legacy)


def unique_by_day(con, days: list[int], server: str | None = None) -> list[int]:
    out = []
    cur = con.cursor()
    srv_sql, srv_args = server_sql(server, "ms.`server_name`")
    for d in days:
        t0 = day_start_ts(d)
        t1 = day_start_ts(add_days(d, 1))
        # day column + wall-clock joins (overnight maps keep yesterday's day).
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT sp.`steam_id`) AS c
            FROM `site_session_players` sp
            INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
            WHERE (ms.`day`=%s OR (sp.`joined_at`>=%s AND sp.`joined_at`<%s)
                   OR (ms.`started_at`>=%s AND ms.`started_at`<%s))
              {srv_sql}
            """,
            (d, t0, t1, t0, t1, *srv_args),
        )
        from_sess = int(cur.fetchone()["c"] or 0)
        _, snap_uniq = _snap_peak_unique(con, d, server)
        out.append(max(from_sess, snap_uniq))
    return out


def peak_by_day(con, days: list[int], server: str | None = None) -> list[int]:
    out = []
    cur = con.cursor()
    srv_sql, srv_args = server_sql(server, "ms.`server_name`")
    for d in days:
        snap_peak, _ = _snap_peak_unique(con, d, server)
        t0 = day_start_ts(d)
        t1 = day_start_ts(add_days(d, 1))
        # Sessions that overlap this calendar day (incl. still open, started recently).
        cur.execute(
            f"""
            SELECT COALESCE(MAX(`player_count`), 0) AS peak
            FROM `site_map_sessions` ms
            WHERE (
                ms.`day`=%s
                OR (
                  ms.`started_at` >= %s AND ms.`started_at` < %s
                  AND (ms.`ended_at`=0 OR ms.`ended_at` >= %s)
                )
              )
              {srv_sql}{nonempty_session_sql("ms.`player_count`")}
            """,
            (d, t0 - 86400, t1, t0, *srv_args),
        )
        sess_peak = int(cur.fetchone()["peak"] or 0)
        if server:
            out.append(max(snap_peak, sess_peak))
        else:
            out.append(max(snap_peak, sess_peak) if snap_peak == 0 else snap_peak)
    return out


def players_on_day(con, day: int, server: str | None = None) -> set[str]:
    cur = con.cursor()
    srv_sql, srv_args = server_sql(server, "ms.`server_name`")
    cur.execute(
        f"""
        SELECT DISTINCT sp.`steam_id`
        FROM `site_session_players` sp
        INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
        WHERE ms.`day`=%s{srv_sql}
        """,
        (day, *srv_args),
    )
    return {str(r["steam_id"]) for r in cur.fetchall()}


def retention(
    con, days: list[int], offset: int, server: str | None = None
) -> list[float | None]:
    cache: dict[int, set[str]] = {}

    def get(d: int) -> set[str]:
        if d not in cache:
            cache[d] = players_on_day(con, d, server)
        return cache[d]

    out: list[float | None] = []
    for d in days:
        cohort = get(d)
        if not cohort:
            out.append(None)
            continue
        later = get(add_days(d, offset))
        hit = sum(1 for sid in cohort if sid in later)
        out.append(round(1000.0 * hit / len(cohort)) / 10.0)
    return out


def avg_playtime_by_day(con, days: list[int], server: str | None = None) -> list[int]:
    out = []
    cur = con.cursor()
    srv_sql, srv_args = server_sql(server, "ms.`server_name`")
    for d in days:
        cur.execute(
            f"""
            SELECT sp.`steam_id`, SUM(sp.`duration_sec`) AS total
            FROM `site_session_players` sp
            INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
            WHERE ms.`day`=%s{srv_sql}
            GROUP BY sp.`steam_id`
            """,
            (d, *srv_args),
        )
        rows = cur.fetchall()
        if not rows:
            out.append(0)
            continue
        total = sum(int(r["total"] or 0) for r in rows)
        out.append(int(round(total / len(rows))))
    return out


def build_summary(con, server: str | None = None) -> dict[str, Any]:
    today = day_from_ts(now_ts())
    min_day = add_days(today, -(DAYS - 1))
    dl = parse_download_stats(min_day)
    srv_sql, srv_args = server_sql(server)
    with LOCK:
        days = day_list(con, min_day, list(dl["by_day"].keys()), server)
        unique = unique_by_day(con, days, server)
        peak = peak_by_day(con, days, server)
        retention_d1 = retention(con, days, 1, server)
        retention_d7 = retention(con, days, 7, server)
        avg_playtime_sec = avg_playtime_by_day(con, days, server)
        downloads = [int(dl["by_day"].get(d, 0)) for d in days]
        cur = con.cursor()
        ms_srv_sql, ms_srv_args = server_sql(server, "ms.`server_name`")
        cur.execute(
            f"SELECT COUNT(*) AS c FROM `site_map_sessions` WHERE 1=1{srv_sql}{nonempty_session_sql()}",
            srv_args,
        )
        sessions = int(cur.fetchone()["c"] or 0)
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT sp.`steam_id`) AS c
            FROM `site_session_players` sp
            INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
            WHERE 1=1{ms_srv_sql}{nonempty_session_sql("ms.`player_count`")}
            """,
            ms_srv_args,
        )
        players = int(cur.fetchone()["c"] or 0)
        cur.execute(
            f"""
            SELECT sp.`perk_name` AS name, COUNT(*) AS c
            FROM `site_session_players` sp
            INNER JOIN `site_map_sessions` ms ON ms.`id`=sp.`session_id`
            WHERE sp.`perk_name` != ''{ms_srv_sql}{nonempty_session_sql("ms.`player_count`")}
            GROUP BY sp.`perk_name`
            ORDER BY c DESC LIMIT 12
            """,
            ms_srv_args,
        )
        perks = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            f"""
            SELECT `map_name` AS name, COUNT(*) AS c FROM `site_map_sessions`
            WHERE `map_name` != ''{srv_sql}{nonempty_session_sql()}
            GROUP BY `map_name`
            ORDER BY c DESC LIMIT 12
            """,
            srv_args,
        )
        maps = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            f"""
            SELECT `outcome` AS name, COUNT(*) AS c FROM `site_map_sessions`
            WHERE 1=1{srv_sql}{nonempty_session_sql()}
            GROUP BY `outcome`
            """,
            srv_args,
        )
        outcomes = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            f"""
            SELECT `wave` AS name, COUNT(*) AS c FROM `site_map_sessions`
            WHERE `outcome`='loss' AND `wave`>0{srv_sql}{nonempty_session_sql()}
            GROUP BY `wave` ORDER BY `wave` LIMIT 20
            """,
            srv_args,
        )
        loss_waves = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        servers = list_servers(con)
        today_idx = days.index(today) if today in days else -1
        if today_idx >= 0:
            today_unique = unique[today_idx]
            today_peak = peak[today_idx]
        else:
            today_unique = unique_by_day(con, [today], server)[0]
            today_peak = peak_by_day(con, [today], server)[0]

    SERVER_TAB_LABELS = {
        "normal": "Normal",
        "hard": "Hard",
        "suicidal": "Suicidal",
        "hoe": "HoE",
    }
    return {
        "server": server or "",
        "serverTabs": [{"name": "", "label": "Все"}]
        + [
            {"name": s, "label": SERVER_TAB_LABELS.get(s, s)}
            for s in KNOWN_SERVERS
        ],
        "days": days,
        "peak": peak,
        "unique": unique,
        "retention_d1": retention_d1,
        "retention_d7": retention_d7,
        "avg_playtime_sec": avg_playtime_sec,
        "downloads": downloads,
        "downloadsTotal": int(dl["total"]),
        "downloadsToday": int(dl["today"]),
        "downloadsByPath": [
            {"name": k, "c": v}
            for k, v in sorted(dl["by_path"].items(), key=lambda kv: -kv[1])
        ],
        "todayPeak": today_peak,
        "todayUnique": today_unique,
        "sessions": sessions,
        "players": players,
        "perks": perks,
        "maps": maps,
        "outcomes": outcomes,
        "loss_waves": loss_waves,
        "servers": servers,
    }


def migrate_sqlite_if_any(con) -> None:
    """One-shot: copy daily snapshots from the abandoned sqlite file."""
    path = Path(os.environ.get("STATS_DB_LEGACY", "/var/lib/kfm-site/stats.sqlite"))
    if not path.is_file():
        return
    try:
        import sqlite3

        sq = sqlite3.connect(str(path))
        sq.row_factory = sqlite3.Row
        rows = sq.execute(
            "SELECT day, peak, unique_count, updated_at FROM daily_snapshot"
        ).fetchall()
        with LOCK:
            cur = con.cursor()
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO `site_daily_snapshot`
                      (`day`, `server_name`, `peak`, `unique_count`, `updated_at`)
                    VALUES(%s,'',%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      `peak`=GREATEST(`peak`, VALUES(`peak`)),
                      `unique_count`=GREATEST(`unique_count`, VALUES(`unique_count`)),
                      `updated_at`=VALUES(`updated_at`)
                    """,
                    (int(r["day"]), int(r["peak"]), int(r["unique_count"]), int(r["updated_at"])),
                )
        sq.close()
        print(f"migrated {len(rows)} daily rows from {path}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"sqlite migrate skipped: {exc}", flush=True)


def ingest_payload(con, body: dict[str, Any]) -> str:
    """Apply one ingest body. Returns type label for logs."""
    typ = str(body.get("type") or "").lower()
    if typ in ("daily", "snapshot"):
        ingest_daily(con, body)
        return "daily"
    if typ in ("map_open", "map"):
        ingest_map_open(con, body)
        return "map_open"
    if typ == "map_close":
        ingest_map_close(con, body)
        return "map_close"
    if typ in ("player_join", "join"):
        ingest_player_join(con, body)
        return "player_join"
    if typ in ("player_leave", "leave", "player"):
        ingest_player_leave(con, body)
        return "player_leave"
    if typ == "live":
        ingest_live(con, body)
        return "live"
    # Legacy per-player session payloads ignored (schema is map-first now).
    if typ in ("session", "batch", ""):
        return "ignored_legacy"
    raise ValueError(f"unknown type: {typ}")


class Handler(BaseHTTPRequestHandler):
    server_version = "KFMStats/1.2"
    con = None  # set in main

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def _send(self, code: int, body: Any, ctype: str = "application/json; charset=utf-8") -> None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        if path in ("/health", "/api/stats/health"):
            self._send(200, {"ok": True, "db": mysql_cfg()["db"]})
            return
        if path in ("/statistics", "/statistics/index.html"):
            html = HTML_PATH.read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/stats/summary":
            server = normalize_server((qs.get("server") or [None])[0])
            self._send(200, build_summary(self.con, server))
            return
        if path == "/api/stats/load":
            server = normalize_server((qs.get("server") or [None])[0])
            self._send(200, build_load_series(server))
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/stats/ingest":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            self._send(413, {"error": "body too large"})
            return
        raw = self.rfile.read(length) if length else b""
        body = parse_body(raw, self.headers.get("Content-Type", ""))
        try:
            typ = ingest_payload(self.con, body)
            print(f"ingest http type={typ}", flush=True)
            self._send(200, {"ok": True})
        except Exception as exc:  # noqa: BLE001
            self._send(400, {"error": str(exc)})


def udp_ingest_loop(con) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    print(f"kfm-stats udp ingest on {HOST}:{PORT}", flush=True)
    while True:
        try:
            raw, addr = sock.recvfrom(65535)
        except OSError as exc:
            print(f"udp recv error: {exc}", flush=True)
            time.sleep(0.5)
            continue
        if not raw:
            continue
        body = parse_body(raw, "application/x-www-form-urlencoded")
        try:
            typ = ingest_payload(con, body)
            print(f"ingest udp type={typ} from={addr[0]}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"ingest udp error from={addr[0]}: {exc}", flush=True)


def load_env_files() -> None:
    for path in (
        Path("/etc/kfm-site.env"),
        Path("/home/kfserver/.kfm-save.env"),
    ):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    load_env_files()
    con = connect()
    init_schema(con)
    migrate_sqlite_if_any(con)
    Handler.con = con
    threading.Thread(target=udp_ingest_loop, args=(con,), name="stats-udp", daemon=True).start()
    threading.Thread(target=load_sampler_loop, name="stats-load", daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    cfg = mysql_cfg()
    print(
        f"kfm-stats listening http+udp://{HOST}:{PORT} "
        f"mysql={cfg['user']}@{cfg['host']}/{cfg['db']} days={DAYS} "
        f"load={LOAD_INTERVAL_SEC}s keep={LOAD_KEEP}",
        flush=True,
    )
    httpd.serve_forever()


if __name__ == "__main__":
    main()
