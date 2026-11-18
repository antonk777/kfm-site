import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("stats_staging", Path(__file__).resolve().parents[1] / "stats-server.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


class StagingStatsTests(unittest.TestCase):
    def setUp(self):
        slots = stats._default_panel() + [stats.PanelServer("staging", "Staging", "host", 7727, 7728, "staging")]
        for name, value in {"_PANEL": slots, "_LIVE": {}, "_TICK_SAMPLES": {}, "_LIVE_DAILY_PEAK": {}}.items():
            fixture = patch.object(stats, name, value)
            fixture.start()
            self.addCleanup(fixture.stop)

    def test_staging_history_is_excluded(self):
        db = Mock()
        for kind in ("map_open", "map_close", "player_join", "player_leave", "map_clear", "daily"):
            with self.subTest(kind=kind):
                self.assertEqual(stats._ingest_payload(db, {"type": kind, "key": "staging:KF-Test:1"}), "ignored_staging")
        self.assertNotIn("staging", stats.server_sql(None)[1])
        self.assertEqual(stats.server_sql("staging"), (" AND 1=0", ()))
        self.assertEqual(stats.day_list(db, 20261118, server="staging"), [])
        self.assertEqual(stats._snap_numbers(db, 20261118, "staging"), (0, 0))
        db.cursor.assert_not_called()

    def test_live_staging_status_stays_available_without_affecting_peaks(self):
        db = Mock()
        with patch.object(stats, "_parse_live_players", side_effect=[["tester"], ["player"]]), \
             patch.object(stats, "peak_by_day", return_value=[0]), \
             patch.object(stats, "close_replaced_sessions") as close_sessions:
            stats.ingest_live(db, {"server": "staging", "key": "staging:KF-Test:1", "debug": "1", "revision": "3S"})
            db.cursor.assert_not_called()
            close_sessions.assert_not_called()
            self.assertEqual(stats._LIVE["staging"]["revision"], "3S")
            self.assertEqual(stats._LIVE["staging"]["online"], 1)
            self.assertEqual(stats._LIVE["staging"]["sessionKey"], "")
            stats.ingest_live(db, {"server": "meatgrinder"})
            self.assertEqual(db.cursor().execute.call_args.args[1][2], 1)


if __name__ == "__main__":
    unittest.main()
