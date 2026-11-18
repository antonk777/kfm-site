"""Coverage for the load measurements displayed on the private server cards."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("stats_load", Path(__file__).resolve().parents[1] / "stats-server.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


class ServerLoadTests(unittest.TestCase):
    def test_shared_vps_keeps_separate_process_rates_and_restart_gaps(self):
        slots = ("condemned", "staging")
        group = {"id": "de", "ssh": "node", "servers": slots}

        def counters(t, a, b, start=16):
            return {
                "idle": 20, "total": t * 100, "mem": 62, "net": t * 1000,
                "mem_total": 2048000, "hz": 100, "clock": t,
                "processes": {
                    slots[0]: {"pid": 21, "start": 9, "jiffies": a, "rss_kb": 307200, "net": t * 125000},
                    slots[1]: {"pid": 42, "start": start, "jiffies": b, "rss_kb": 204800, "net": 0},
                },
            }

        with (
            patch.object(stats, "KNOWN_SERVERS", ()),
            patch.object(stats, "panel_ids", return_value=slots),
            patch.object(stats, "host_groups", return_value=[group]),
            patch.object(stats, "_REMOTE_PREV", {}),
            patch.object(stats, "_REMOTE_SAMPLES", {}),
            patch.object(stats, "_REMOTE_PROC_SAMPLES", {}),
            patch.object(stats, "get_live_status", return_value={}),
        ):
            stats._accept_remote_counters("de", counters(100, 200, 100), slots)
            stats._accept_remote_counters("de", counters(102, 250, 120), slots)
            result = stats.build_load_series("condemned")
            self.assertEqual(result["scope"], "process")
            self.assertEqual(result["now"]["core_pct"], 25)
            self.assertEqual(result["now"]["net_mbps"], 1.0)
            self.assertEqual(result["slotLoad"]["staging"]["now"]["core_pct"], 10)
            self.assertEqual(result["slotLoad"]["staging"]["now"]["mem_mb"], 200)
            self.assertEqual(result["hosts"][0]["scope"], "host")
            stats._accept_remote_counters("de", counters(104, 300, 1, start=103), slots)
            result = stats.build_load_series("staging")
            self.assertIsNone(result["now"])
            self.assertEqual(result["cpu"], [10, None])
            self.assertIsNotNone(result["slotLoad"]["condemned"]["now"])

    def test_process_measurements_use_cpu_ticks_and_require_both_network_reads(self):
        slot = "test"
        with (
            patch.object(stats, "KNOWN_SERVERS", (slot,)),
            patch.object(stats, "_PROC_PREV", {}),
            patch.object(stats, "_PROC_SAMPLES", {slot: []}),
            patch.object(stats, "_resolve_slot_pid", return_value=100),
            patch.object(stats, "_read_pid_rss_kb", return_value=262144),
            patch.object(stats, "_read_pid_cpu_jiffies", side_effect=[400, 500, 550, 750]),
            patch.object(stats.os, "sysconf", return_value=100, create=True),
            patch.object(stats, "_slot_net_bytes", side_effect=[{slot: 0}, {slot: 250000}, {}, {slot: 800000}]),
        ):
            for tick in range(4):
                stats._sample_slot_load(100 + tick * 2, 3200 + tick * 800, 1048576)
            first, missing, resumed = stats._PROC_SAMPLES[slot]
            self.assertEqual((first["cpu_seconds"], first["core_pct"], first["cpu"]), (5, 50, 12.5))
            self.assertEqual((first["mem_mb"], first["net_mbps"]), (256, 1))
            self.assertIsNone(missing["net_mbps"])
            self.assertIsNone(resumed["net_mbps"])

    def test_cards_get_current_process_or_remote_host_measurements(self):
        groups = [{"id": "local", "ssh": "", "servers": ["a", "b"]},
                  {"id": "remote", "ssh": "remote", "servers": ["c"]}]
        local = {"ts": 98, "cpu": 4, "mem": 25, "net_mbps": None}
        remote = {"ts": 96, "cpu": 12, "mem": 33, "net_mbps": 1}
        with (
            patch.object(stats, "KNOWN_SERVERS", ("a", "b")),
            patch.object(stats, "panel_ids", return_value=("a", "b", "c")),
            patch.object(stats, "host_groups", return_value=groups),
            patch.object(stats, "_PROC_SAMPLES", {"a": [local], "b": [dict(local, ts=10)]}),
            patch.object(stats, "_REMOTE_SAMPLES", {"remote": [remote]}),
            patch.object(stats, "get_live_status", return_value={}),
            patch.object(stats.time, "time", return_value=100),
        ):
            rows = stats.build_load_series()["slotLoad"]
            self.assertEqual(rows["a"], {"scope": "process", "now": local})
            self.assertEqual(rows["b"], {"scope": "process", "now": None})
            self.assertEqual(rows["c"], {"scope": "host", "now": remote})
