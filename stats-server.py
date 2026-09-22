#!/usr/bin/env python3
"""KF-Maniacs secret statistics API + /statistics/ charts.

Uses the same MariaDB as perkhost (kfmaniacs). New tables:
  site_play_sessions, site_daily_snapshot
Players come from the existing `players` table (steam_id).

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
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus, urlparse

HOST = os.environ.get("STATS_HOST", "127.0.0.1")
PORT = int(os.environ.get("STATS_PORT", "8765"))
DAYS = max(30, int(os.environ.get("STATS_DAYS", "180")))
HTML_PATH = Path(__file__).with_name("statistics.html")
LOCK = threading.Lock()
DOWNLOAD_PATH_RE = re.compile(r"^/(download|KFM-Companion[^/]*\.exe)$", re.I)
_DOWNLOAD_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_DOWNLOAD_CACHE_TTL = 60.0


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
        CREATE TABLE IF NOT EXISTS `site_play_sessions` (
          `id` BIGINT NOT NULL AUTO_INCREMENT,
          `steam_id` VARCHAR(64) NOT NULL,
          `name` VARCHAR(64) NOT NULL DEFAULT '',
          `started_at` INT NOT NULL,
          `ended_at` INT NOT NULL,
          `duration_sec` INT NOT NULL DEFAULT 0,
          `map_name` VARCHAR(64) NOT NULL DEFAULT '',
          `perk_index` INT NOT NULL DEFAULT -1,
          `perk_name` VARCHAR(32) NOT NULL DEFAULT '',
          `outcome` VARCHAR(16) NOT NULL DEFAULT 'unknown',
          `wave` INT NOT NULL DEFAULT 0,
          `final_wave` INT NOT NULL DEFAULT 0,
          `difficulty` DOUBLE NOT NULL DEFAULT 0,
          `day` INT NOT NULL,
          `server_name` VARCHAR(64) NOT NULL DEFAULT '',
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_site_session` (`steam_id`, `started_at`, `map_name`),
          KEY `idx_site_sess_day` (`day`),
          KEY `idx_site_sess_steam_day` (`steam_id`, `day`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    # Older installs used (steam, started, map, outcome) — drop outcome from unique
    # so leave→rejoin merges can upsert the same session row.
    try:
        cur.execute("SHOW INDEX FROM `site_play_sessions` WHERE Key_name='uk_site_session'")
        cols = [r["Column_name"] for r in cur.fetchall()]
        if cols and "outcome" in cols:
            cur.execute("ALTER TABLE `site_play_sessions` DROP INDEX `uk_site_session`")
            cur.execute(
                "ALTER TABLE `site_play_sessions` "
                "ADD UNIQUE KEY `uk_site_session` (`steam_id`, `started_at`, `map_name`)"
            )
            print("migrated uk_site_session without outcome", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"uk_site_session migrate skipped: {exc}", flush=True)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS `site_daily_snapshot` (
          `day` INT NOT NULL,
          `peak` INT NOT NULL DEFAULT 0,
          `unique_count` INT NOT NULL DEFAULT 0,
          `updated_at` INT NOT NULL,
          PRIMARY KEY (`day`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


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


def ingest_session(con, p: dict[str, Any]) -> None:
    steam = str(p.get("steam") or p.get("steam_id") or "").strip()
    if not steam:
        raise ValueError("steam required")
    ended = int(num(p.get("ended_at"), now_ts()))
    duration = max(0, int(num(p.get("duration"), num(p.get("duration_sec"), 0))))
    started = int(num(p.get("started_at"), ended - duration))
    day = int(num(p.get("day"), day_from_ts(ended or now_ts())))
    name = str(p.get("name") or p.get("player") or "")[:64]
    map_name = str(p.get("map") or p.get("map_name") or "")[:64]
    perk_name = str(p.get("perk") or p.get("perk_name") or "")[:32]
    outcome = str(p.get("outcome") or "unknown").lower()[:16]
    perk_index = int(num(p.get("perkIdx"), num(p.get("perk_index"), -1)))
    wave = int(num(p.get("wave"), 0))
    final_wave = int(num(p.get("finalWave"), num(p.get("final_wave"), 0)))
    difficulty = float(num(p.get("diff"), num(p.get("difficulty"), 0.0)))
    server_name = str(p.get("server") or p.get("server_name") or "")[:64]
    with LOCK:
        touch_player(con, steam, name)
        con.cursor().execute(
            """
            INSERT INTO `site_play_sessions`(
              `steam_id`, `name`, `started_at`, `ended_at`, `duration_sec`,
              `map_name`, `perk_index`, `perk_name`, `outcome`, `wave`, `final_wave`,
              `difficulty`, `day`, `server_name`
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              `name`=VALUES(`name`),
              `ended_at`=GREATEST(`ended_at`, VALUES(`ended_at`)),
              `duration_sec`=GREATEST(`duration_sec`, VALUES(`duration_sec`)),
              `perk_index`=IF(VALUES(`perk_name`)='', `perk_index`, VALUES(`perk_index`)),
              `perk_name`=IF(VALUES(`perk_name`)='', `perk_name`, VALUES(`perk_name`)),
              `outcome`=VALUES(`outcome`),
              `wave`=GREATEST(`wave`, VALUES(`wave`)),
              `final_wave`=GREATEST(`final_wave`, VALUES(`final_wave`)),
              `difficulty`=VALUES(`difficulty`),
              `day`=VALUES(`day`),
              `server_name`=IF(VALUES(`server_name`)='', `server_name`, VALUES(`server_name`))
            """,
            (
                steam,
                name,
                started,
                ended,
                duration,
                map_name,
                perk_index,
                perk_name,
                outcome,
                wave,
                final_wave,
                difficulty,
                day,
                server_name,
            ),
        )


def ingest_daily(con, p: dict[str, Any]) -> None:
    day = int(num(p.get("day"), 0))
    if day <= 0:
        raise ValueError("day required")
    with LOCK:
        con.cursor().execute(
            """
            INSERT INTO `site_daily_snapshot`(`day`, `peak`, `unique_count`, `updated_at`)
            VALUES(%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              `peak`=GREATEST(`peak`, VALUES(`peak`)),
              `unique_count`=GREATEST(`unique_count`, VALUES(`unique_count`)),
              `updated_at`=VALUES(`updated_at`)
            """,
            (
                day,
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


def day_list(con, min_day: int, extra_days: list[int] | None = None) -> list[int]:
    cur = con.cursor()
    cur.execute(
        """
        SELECT DISTINCT `day` FROM (
          SELECT `day` FROM `site_play_sessions` WHERE `day` >= %s
          UNION
          SELECT `day` FROM `site_daily_snapshot` WHERE `day` >= %s
        ) t ORDER BY `day`
        """,
        (min_day, min_day),
    )
    days = {int(r["day"]) for r in cur.fetchall()}
    if extra_days:
        for d in extra_days:
            if d >= min_day:
                days.add(int(d))
    return sorted(days)


def unique_by_day(con, days: list[int]) -> list[int]:
    out = []
    cur = con.cursor()
    for d in days:
        cur.execute(
            "SELECT COUNT(DISTINCT `steam_id`) AS c FROM `site_play_sessions` WHERE `day`=%s",
            (d,),
        )
        from_sess = int(cur.fetchone()["c"] or 0)
        cur.execute(
            "SELECT `unique_count` FROM `site_daily_snapshot` WHERE `day`=%s", (d,)
        )
        snap = cur.fetchone()
        out.append(max(from_sess, int(snap["unique_count"] if snap else 0)))
    return out


def peak_by_day(con, days: list[int]) -> list[int]:
    out = []
    cur = con.cursor()
    for d in days:
        cur.execute("SELECT `peak` FROM `site_daily_snapshot` WHERE `day`=%s", (d,))
        snap = cur.fetchone()
        out.append(int(snap["peak"]) if snap else 0)
    return out


def players_on_day(con, day: int) -> set[str]:
    cur = con.cursor()
    cur.execute(
        "SELECT DISTINCT `steam_id` FROM `site_play_sessions` WHERE `day`=%s", (day,)
    )
    return {str(r["steam_id"]) for r in cur.fetchall()}


def retention(con, days: list[int], offset: int) -> list[float | None]:
    cache: dict[int, set[str]] = {}

    def get(d: int) -> set[str]:
        if d not in cache:
            cache[d] = players_on_day(con, d)
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


def avg_playtime_by_day(con, days: list[int]) -> list[int]:
    out = []
    cur = con.cursor()
    for d in days:
        cur.execute(
            """
            SELECT `steam_id`, SUM(`duration_sec`) AS total
            FROM `site_play_sessions` WHERE `day`=%s
            GROUP BY `steam_id`
            """,
            (d,),
        )
        rows = cur.fetchall()
        if not rows:
            out.append(0)
            continue
        total = sum(int(r["total"] or 0) for r in rows)
        out.append(int(round(total / len(rows))))
    return out


def build_summary(con) -> dict[str, Any]:
    today = day_from_ts(now_ts())
    min_day = add_days(today, -(DAYS - 1))
    dl = parse_download_stats(min_day)
    with LOCK:
        days = day_list(con, min_day, list(dl["by_day"].keys()))
        unique = unique_by_day(con, days)
        peak = peak_by_day(con, days)
        retention_d1 = retention(con, days, 1)
        retention_d7 = retention(con, days, 7)
        avg_playtime_sec = avg_playtime_by_day(con, days)
        downloads = [int(dl["by_day"].get(d, 0)) for d in days]
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM `site_play_sessions`")
        sessions = int(cur.fetchone()["c"] or 0)
        # Known Steam accounts that appear in site sessions OR perkhost players
        # who have played (have any site session). Count distinct steam in sessions.
        cur.execute("SELECT COUNT(DISTINCT `steam_id`) AS c FROM `site_play_sessions`")
        players = int(cur.fetchone()["c"] or 0)
        cur.execute(
            """
            SELECT `perk_name` AS name, COUNT(*) AS c FROM `site_play_sessions`
            WHERE `perk_name` != '' GROUP BY `perk_name`
            ORDER BY c DESC LIMIT 12
            """
        )
        perks = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            """
            SELECT `map_name` AS name, COUNT(*) AS c FROM `site_play_sessions`
            WHERE `map_name` != '' GROUP BY `map_name`
            ORDER BY c DESC LIMIT 12
            """
        )
        maps = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            "SELECT `outcome` AS name, COUNT(*) AS c FROM `site_play_sessions` GROUP BY `outcome`"
        )
        outcomes = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        cur.execute(
            """
            SELECT `wave` AS name, COUNT(*) AS c FROM `site_play_sessions`
            WHERE `outcome`='loss' AND `wave`>0
            GROUP BY `wave` ORDER BY `wave` LIMIT 20
            """
        )
        loss_waves = [{"name": r["name"], "c": int(r["c"])} for r in cur.fetchall()]
        today_idx = days.index(today) if today in days else -1
        if today_idx >= 0:
            today_unique = unique[today_idx]
            today_peak = peak[today_idx]
        else:
            today_unique = unique_by_day(con, [today])[0]
            today_peak = peak_by_day(con, [today])[0]

    return {
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
                    INSERT INTO `site_daily_snapshot`(`day`, `peak`, `unique_count`, `updated_at`)
                    VALUES(%s,%s,%s,%s)
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
    typ = str(body.get("type") or "session").lower()
    if typ in ("daily", "snapshot"):
        ingest_daily(con, body)
        return "daily"
    if typ == "batch" and isinstance(body.get("sessions"), list):
        for s in body["sessions"]:
            if isinstance(s, dict):
                ingest_session(con, s)
        return "batch"
    ingest_session(con, body)
    return "session"


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
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/api/stats/health"):
            self._send(200, {"ok": True, "db": mysql_cfg()["db"]})
            return
        if path in ("/statistics", "/statistics/index.html"):
            html = HTML_PATH.read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/stats/summary":
            self._send(200, build_summary(self.con))
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
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    cfg = mysql_cfg()
    print(
        f"kfm-stats listening http+udp://{HOST}:{PORT} "
        f"mysql={cfg['user']}@{cfg['host']}/{cfg['db']} days={DAYS}",
        flush=True,
    )
    httpd.serve_forever()


if __name__ == "__main__":
    main()
