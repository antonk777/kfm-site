"""Ban workflow and HTTP authorization regression tests, isolated from live data.

SQLite executes the queries through a small MariaDB syntax adapter. Production
row locking and engine-specific behavior still need MariaDB integration coverage.
"""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("stats_bans", Path(__file__).resolve().parents[1] / "stats-server.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)
ADMIN = "76561198000000001"
PLAYER = "76561198000000002"


class Cursor:
    def __init__(self, db):
        self.cur = db.cursor()

    def execute(self, sql, args=()):
        self.cur.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), args)
        return self

    def fetchone(self):
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cur.fetchall()]

    @property
    def lastrowid(self):
        return self.cur.lastrowid


class Database:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False,
                                  detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("UTC_TIMESTAMP", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        self.db.create_function("LOCATE", 2, lambda needle, text: (text or "").casefold().find(needle.casefold()) + 1)
        self.db.executescript("""
            CREATE TABLE players (id INTEGER PRIMARY KEY, last_player_name TEXT, steam_id TEXT, admin INTEGER DEFAULT 0);
            CREATE TABLE bans (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, until_at TIMESTAMP,
                duration_range INTEGER DEFAULT 5, duration_value REAL DEFAULT 0, reason TEXT DEFAULT '',
                admin_name TEXT DEFAULT '', admin_id INTEGER DEFAULT 0, active INTEGER DEFAULT 1, unbanned_at TIMESTAMP);
            CREATE TABLE site_ban_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ban_id INTEGER,
                action TEXT, actor_id INTEGER, actor_name TEXT, changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                before_json TEXT, after_json TEXT);
        """)
        self.db.executemany("INSERT INTO players VALUES (?, ?, ?, ?)", [
            (1, "Moderator", ADMIN, 1), (2, "Test player", PLAYER, 0),
            (3, "Other admin", "76561198000000003", 1), (4, "100%_literal", "76561198000000004", 0)])

    def cursor(self): return Cursor(self.db)
    def ping(self, **_): pass
    def begin(self): self.db.execute("BEGIN")
    def commit(self): self.db.commit()
    def rollback(self): self.db.rollback()


class BanTests(unittest.TestCase):
    def setUp(self):
        self.con = Database()
        self.addCleanup(self.con.db.close)

    def create(self, **overrides):
        body = dict(action="create", accountId=2, reason="Repeated griefing", untilAt=None)
        body.update(overrides)
        return stats.admin_change_ban(self.con, ADMIN, body)["ban"]

    def edit(self, ban, **overrides):
        body = dict(action="edit", banId=ban["id"], version=ban["version"], reason="Updated reason", untilAt=None)
        body.update(overrides)
        return stats.admin_change_ban(self.con, ADMIN, body)["ban"]

    def test_create_edit_revoke_retains_history_and_actor(self):
        expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        ban = self.create(untilAt=expiry, adminId=999, adminName="Spoof")
        self.assertEqual(ban["adminName"], "Moderator")
        self.assertEqual(ban["adminId"], 1)
        self.assertTrue(ban["untilAt"].endswith("Z"))
        updated = self.edit(ban)
        self.assertIsNone(updated["untilAt"])
        result = stats.admin_change_ban(self.con, ADMIN, dict(action="revoke", banId=ban["id"], version=updated["version"]))
        self.assertEqual(result["ban"]["status"], "revoked")
        self.assertEqual(stats.admin_bans(self.con)["total"], 0)
        self.assertEqual(stats.admin_bans(self.con, status="revoked")["total"], 1)
        events = stats.admin_ban_history(self.con, ban["id"])["events"]
        self.assertEqual([e["action"] for e in events], ["revoke", "edit", "create"])
        self.assertEqual(events[1]["before"]["reason"], "Repeated griefing")
        self.assertEqual(events[1]["after"]["reason"], "Updated reason")
        self.assertEqual(self.create()["status"], "active")
        self.assertEqual(stats.admin_bans(self.con, status="all")["total"], 2)

    def test_duplicate_and_stale_edit_cannot_overwrite(self):
        ban = self.create()
        with self.assertRaisesRegex(stats.BanError, "already_banned"): self.create()
        self.edit(ban)
        with self.assertRaisesRegex(stats.BanError, "ban_changed"): self.edit(ban, reason="Stale")
        self.assertEqual(stats.admin_bans(self.con)["bans"][0]["reason"], "Updated reason")

    def test_admin_check_and_target_protection(self):
        for sid in (PLAYER, "76561198000000999"):
            with self.assertRaisesRegex(stats.BanError, "auth_required"):
                stats.admin_change_ban(self.con, sid, dict(action="create", accountId=4, reason="Reason", untilAt=None))
        for target in (1, 3):
            with self.assertRaisesRegex(stats.BanError, "admin_target"): self.create(accountId=target)
        ban = self.create()
        self.con.db.execute("UPDATE players SET admin=1 WHERE id=2")
        with self.assertRaisesRegex(stats.BanError, "admin_target"): self.edit(ban)
        # An accidentally banned admin can still be unbanned.
        stats.admin_change_ban(self.con, ADMIN, dict(action="revoke", banId=ban["id"], version=ban["version"]))

    def test_validation_leaves_no_partial_data(self):
        invalid = [dict(reason=""), dict(reason="x" * 121), dict(reason="a\nb"), dict(reason="a|b"),
                   dict(untilAt="2020-01-01T00:00:00Z"), dict(untilAt="2099-01-01T00:00:00"),
                   dict(untilAt="bad"), dict(untilAt=1), dict(accountId=True), dict(accountId=-1), dict(accountId=999)]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(stats.BanError): self.create(**body)
        with self.assertRaises(stats.BanError):
            stats.admin_change_ban(self.con, ADMIN, dict(action="create", accountId=2, reason="Reason"))
        self.assertEqual(stats.admin_bans(self.con, status="all")["total"], 0)

    def test_audit_failure_rolls_back_ban(self):
        self.con.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON site_ban_audit BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.create()
        self.assertEqual(stats.admin_bans(self.con, status="all")["total"], 0)

    def test_expired_bans_are_not_active_even_before_perkhost_cleanup(self):
        ban = self.create()
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        self.con.db.execute("UPDATE bans SET until_at=? WHERE id=?", (past, ban["id"]))
        self.assertEqual(stats.admin_bans(self.con)["total"], 0)
        self.assertEqual(stats.admin_bans(self.con, status="expired")["total"], 1)
        self.assertFalse(stats.admin_ban_players(self.con, PLAYER)["players"][0]["banned"])
        self.create()
        self.assertEqual(stats.admin_bans(self.con, status="expired")["total"], 1)
        self.assertEqual(stats.admin_bans(self.con)["total"], 1)

    def test_search_literal_ids_unicode_and_pagination(self):
        self.create(reason="Оскорбления")
        for q in ("test", PLAYER, "2"):
            self.assertEqual(stats.admin_bans(self.con, q)["total"], 1)
        self.assertEqual(stats.admin_bans(self.con, "' OR 1=1 --")["total"], 0)
        self.assertEqual([p["accountId"] for p in stats.admin_ban_players(self.con, "%_")["players"]], [4])
        self.assertEqual(stats.admin_ban_players(self.con, "")["players"], [])
        for i in range(30):
            self.con.db.execute("INSERT INTO bans (account_id, active) VALUES (4, 0)")
        first = stats.admin_bans(self.con, status="all")
        last = stats.admin_bans(self.con, status="all", page=99)
        self.assertEqual((first["total"], len(first["bans"]), last["page"], len(last["bans"])), (31, 25, 2, 6))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {"STATS_ADMIN_SECRET": "isolated-test-secret"})
        cls.env.start()
        cls.con = Database()
        class Handler(stats.Handler):
            con = cls.con
            def log_message(self, *_): pass
        cls.server = stats.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.con.db.close()
        cls.env.stop()

    def request(self, path, sid=None, body=None, headers=None, token=None):
        h = {"Content-Type": "application/json", "X-KFM-Admin": "1"}
        if sid or token: h["Cookie"] = f"{stats.PLAYER_COOKIE}={token or stats.player_cookie_value(sid)}"
        h.update(headers or {})
        con = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        con.request("POST" if body is not None else "GET", "/api/stats/admin/" + path, json.dumps(body) if body is not None else None, h)
        res = con.getresponse()
        status, payload = res.status, json.loads(res.read())
        self.assertEqual(res.getheader("Cache-Control"), "no-store")
        con.close()
        return status, payload

    def test_all_reads_and_writes_require_signed_current_db_admin(self):
        for path in ("bans", "ban-players?q=test", "ban-history?id=1"):
            for sid in (None, PLAYER):
                with self.subTest(path=path, sid=sid): self.assertEqual(self.request(path, sid)[0], 401)
        self.assertEqual(self.request("bans", token=stats.player_cookie_value(ADMIN) + "tampered")[0], 401)
        self.assertEqual(self.request("bans", ADMIN)[0], 200)
        self.assertEqual(self.request("bans", PLAYER, body={})[0], 401)
        self.con.db.execute("UPDATE players SET admin=0 WHERE id=1")
        try: self.assertEqual(self.request("bans", ADMIN)[0], 401)
        finally: self.con.db.execute("UPDATE players SET admin=1 WHERE id=1")

    def test_csrf_and_invalid_request_rejected(self):
        for headers in ({"X-KFM-Admin": ""}, {"Content-Type": "text/plain"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("bans", ADMIN, body={}, headers=headers)[0], 403)
        self.assertEqual(self.request("bans", ADMIN, body=[])[0], 400)
        self.assertEqual(self.request("bans?page=oops", ADMIN)[0], 400)

    def test_http_create_to_revoke(self):
        code, result = self.request("bans", ADMIN, body=dict(action="create", accountId=2, reason="HTTP test", untilAt=None))
        self.assertEqual(code, 200)
        ban = result["ban"]
        code, result = self.request("bans", ADMIN, body=dict(action="revoke", banId=ban["id"], version=ban["version"]))
        self.assertEqual(code, 200)
        self.assertEqual(result["ban"]["status"], "revoked")

    def test_login_return_path_is_allowlisted(self):
        self.assertEqual(stats.safe_next_path("/admin/bans/"), "/admin/bans")
        for value in ("//evil.example/admin/bans", "https://evil.example", "/admin/bans?next=//evil", "/admin/bans/../outside"):
            self.assertEqual(stats.safe_next_path(value), "")


if __name__ == "__main__":
    unittest.main()
