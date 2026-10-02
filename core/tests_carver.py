"""Engine-level tests for the SQLite carver across every supported schema,
including the guarantee that secret column values never reach the output."""
import json
import os
import random
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from django.test import SimpleTestCase

from core.recovery.sqlite_carver import CarveError, carve_database

CH = datetime(1601, 1, 1)
UX = datetime(1970, 1, 1)
SECRET_PW = "SECRETPASSWORD-9f3a"
SECRET_COOKIE = "SECRETCOOKIEVALUE-77c1"


def cus(dt):
    return int((dt - CH).total_seconds() * 1_000_000)


def uus(dt):
    return int((dt - UX).total_seconds() * 1_000_000)


class _Base(SimpleTestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="dfs_carver_"))
        self.now = datetime.utcnow()

    def db(self, name):
        p = self.d / name
        c = sqlite3.connect(p)
        c.execute("PRAGMA secure_delete=OFF")
        return p, c

    def assert_no_secrets(self, result):
        blob = json.dumps([r.__dict__ for r in result.records], default=str)
        self.assertNotIn(SECRET_PW, blob)
        self.assertNotIn(SECRET_COOKIE, blob)
        for r in result.records:
            if "value" in r.detail:
                self.assertEqual(r.detail["value"], "Protected")


class ChromiumCookiesAndLogins(_Base):
    def test_cookies_recovered_without_values(self):
        p, c = self.db("Cookies")
        c.execute("CREATE TABLE cookies(creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL, "
                  "top_frame_site_key TEXT NOT NULL, name TEXT NOT NULL, value TEXT NOT NULL, "
                  "encrypted_value BLOB NOT NULL, path TEXT NOT NULL, expires_utc INTEGER NOT NULL, "
                  "is_secure INTEGER NOT NULL, is_httponly INTEGER NOT NULL, last_access_utc INTEGER NOT NULL, "
                  "has_expires INTEGER NOT NULL, is_persistent INTEGER NOT NULL, priority INTEGER NOT NULL, "
                  "samesite INTEGER NOT NULL, source_scheme INTEGER NOT NULL, source_port INTEGER NOT NULL, "
                  "last_update_utc INTEGER NOT NULL)")
        rows = []
        for i in range(400):
            t = cus(self.now - timedelta(days=200 - i // 3))
            rows.append((t, f".site{i % 40}.example.com", "", f"sess{i}", SECRET_COOKIE + str(i),
                         (b"v10" + os.urandom(30)), "/", cus(self.now + timedelta(days=30)), 1, i % 2, t,
                         1, 1, 1, -1, 2, 443, t))
        c.executemany("INSERT INTO cookies VALUES (" + ",".join("?" * 18) + ")", rows)
        c.commit()
        c.execute("DELETE FROM cookies WHERE rowid % 3 = 0")
        c.commit()
        c.close()
        deleted = {r[3] for i, r in enumerate(rows) if (i + 1) % 3 == 0}   # rowid = i + 1
        res = carve_database(p)
        got = {r.secondary for r in res.records if r.kind == "cookie"}
        raw = p.read_bytes()
        surviving = {n for n in deleted if n.encode() in raw}
        self.assertGreater(len(surviving), 10)
        self.assertEqual(surviving - got, set(), "cookie remnants present in the file were missed")
        self.assertTrue(got <= {r[3] for r in rows})
        self.assert_no_secrets(res)

    def test_logins_recovered_metadata_only(self):
        p, c = self.db("Login Data")
        c.execute("CREATE TABLE logins (origin_url VARCHAR NOT NULL, action_url VARCHAR, username_element VARCHAR, "
                  "username_value VARCHAR, password_element VARCHAR, password_value BLOB, submit_element VARCHAR, "
                  "signon_realm VARCHAR NOT NULL, date_created INTEGER NOT NULL, blacklisted_by_user INTEGER NOT NULL, "
                  "scheme INTEGER NOT NULL, password_type INTEGER, times_used INTEGER, form_data BLOB, "
                  "date_synced INTEGER, display_name VARCHAR, icon_url VARCHAR, federation_url VARCHAR, "
                  "skip_zero_click INTEGER, generation_upload_status INTEGER, possible_username_pairs BLOB, id INTEGER, "
                  "date_last_used INTEGER NOT NULL DEFAULT 0, moving_blocked_for BLOB, date_password_modified INTEGER)")
        rows = []
        for i in range(120):
            rows.append((f"https://login{i}.example.org/", "", "u", f"user{i}@example.com", "p",
                         SECRET_PW.encode() + os.urandom(20), "", f"https://login{i}.example.org/",
                         cus(self.now - timedelta(days=i)), 0, 0, 0, 1, b"", 0, "", "", "", 0, 0, b"", i, 0, b"", 0))
        c.executemany("INSERT INTO logins VALUES (" + ",".join("?" * 25) + ")", rows)
        c.commit()
        c.execute("DELETE FROM logins WHERE id % 3 = 0")
        c.commit()
        c.close()
        res = carve_database(p)
        got = {r.secondary for r in res.records if r.kind == "login"}
        raw = p.read_bytes()
        surviving = {r[3] for r in rows if r[21] % 3 == 0 and r[3].encode() in raw}
        self.assertGreater(len(surviving), 5)
        self.assertEqual(surviving - got, set())
        self.assert_no_secrets(res)
        self.assertTrue(all(r.detail == {"password": "Protected"} for r in res.records if r.kind == "login"))


class FirefoxSchemas(_Base):
    def test_places_and_cookies(self):
        p, c = self.db("places.sqlite")
        c.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url LONGVARCHAR, title LONGVARCHAR, "
                  "rev_host LONGVARCHAR, visit_count INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0 NOT NULL, "
                  "typed INTEGER DEFAULT 0 NOT NULL, frecency INTEGER DEFAULT -1 NOT NULL, last_visit_date INTEGER, "
                  "guid TEXT, foreign_count INTEGER DEFAULT 0 NOT NULL, url_hash INTEGER DEFAULT 0 NOT NULL)")
        rows = [(i, f"https://ff{i % 31}.example.net/a/{i}", f"Title {i}", "ten.elpmaxe", i % 7, 0, 0, 100,
                 uus(self.now - timedelta(hours=i)), f"guid{i:08d}", 0, i) for i in range(1, 501)]
        c.executemany("INSERT INTO moz_places VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        c.commit()
        c.execute("DELETE FROM moz_places WHERE id % 4 = 0")
        c.commit()
        c.close()
        res = carve_database(p)
        got = {r.primary for r in res.records if r.kind == "history"}
        raw = p.read_bytes()
        surviving = {r[1] for r in rows if r[0] % 4 == 0 and r[1].encode() in raw}
        self.assertGreater(len(surviving), 20)
        self.assertEqual(surviving - got, set())
        self.assertTrue(got <= {r[1] for r in rows})

        p2, c = self.db("cookies.sqlite")
        c.execute("CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, originAttributes TEXT NOT NULL DEFAULT '', "
                  "name TEXT, value TEXT, host TEXT, path TEXT, expiry INTEGER, lastAccessed INTEGER, "
                  "creationTime INTEGER, isSecure INTEGER, isHttpOnly INTEGER, inBrowserElement INTEGER DEFAULT 0, "
                  "sameSite INTEGER DEFAULT 0, rawSameSite INTEGER DEFAULT 0, schemeMap INTEGER DEFAULT 0)")
        crows = [(i, "", f"c{i}", SECRET_COOKIE, f".ck{i % 20}.example.org", "/",
                  int((self.now + timedelta(days=9)).timestamp()), uus(self.now - timedelta(hours=i)),
                  uus(self.now - timedelta(days=1)), 1, 0, 0, 0, 0, 0) for i in range(1, 401)]
        c.executemany("INSERT INTO moz_cookies VALUES (" + ",".join("?" * 15) + ")", crows)
        c.commit()
        c.execute("DELETE FROM moz_cookies WHERE id % 3 = 0")
        c.commit()
        c.close()
        res2 = carve_database(p2)
        got2 = {r.secondary for r in res2.records if r.kind == "cookie"}
        raw2 = p2.read_bytes()
        surv2 = {r[2] for r in crows if r[0] % 3 == 0 and r[2].encode() in raw2}
        self.assertGreater(len(surv2), 10)
        self.assertEqual(surv2 - got2, set())
        self.assert_no_secrets(res2)


class Robustness(_Base):
    def test_not_sqlite_and_empty_and_tiny(self):
        for name, data in (("garbage", os.urandom(20000)), ("empty", b""), ("tiny", b"SQLite format 3\x00" + b"\0" * 20)):
            (self.d / name).write_bytes(data)
            with self.assertRaises(CarveError):
                carve_database(self.d / name)

    def test_unrelated_sqlite_yields_warning_not_records(self):
        p, c = self.db("other.db")
        c.execute("CREATE TABLE t(a,b)")
        c.executemany("INSERT INTO t VALUES (?,?)", [(i, "x" * 30) for i in range(500)])
        c.commit()
        c.execute("DELETE FROM t")
        c.commit()
        c.close()
        res = carve_database(p)
        self.assertEqual(res.records, [])
        self.assertTrue(res.warnings)

    def test_random_page_corruption_never_crashes(self):
        p, c = self.db("H")
        c.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY AUTOINCREMENT,url LONGVARCHAR,title LONGVARCHAR,"
                  "visit_count INTEGER DEFAULT 0 NOT NULL,typed_count INTEGER DEFAULT 0 NOT NULL,"
                  "last_visit_time INTEGER NOT NULL,hidden INTEGER DEFAULT 0 NOT NULL)")
        c.executemany("INSERT INTO urls VALUES (?,?,?,?,?,?,?)",
                      [(i, f"https://e{i}.example.org/{i}", f"t{i}", 1, 0, cus(self.now - timedelta(hours=i)), 0)
                       for i in range(1, 800)])
        c.commit()
        c.execute("DELETE FROM urls WHERE id % 2 = 0")
        c.commit()
        c.close()
        good = p.read_bytes()
        rnd = random.Random(7)
        for trial in range(12):
            b = bytearray(good)
            for _ in range(rnd.randint(1, 6)):
                start = rnd.randrange(100, len(b) - 500)
                for k in range(start, start + rnd.randint(1, 400)):
                    b[k] = rnd.randrange(256)
            if trial % 4 == 3:
                b = b[: rnd.randrange(4096, len(b))]
            (self.d / "fuzz").write_bytes(bytes(b))
            try:
                res = carve_database(self.d / "fuzz")
            except CarveError:
                continue   # damaged header / schema: a clean, reported failure is fine
            for r in res.records:
                self.assertIn(r.confidence, ("high", "medium", "low"))
                self.assertTrue(r.primary.startswith(("http://", "https://")))

    def test_scan_budget_is_enforced(self):
        p, c = self.db("H")
        c.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY,url LONGVARCHAR,title LONGVARCHAR,"
                  "visit_count INTEGER,typed_count INTEGER,last_visit_time INTEGER NOT NULL,hidden INTEGER)")
        c.executemany("INSERT INTO urls VALUES (?,?,?,?,?,?,?)",
                      [(i, f"https://e{i}.example.org/{i}", "t", 1, 0, cus(self.now), 0) for i in range(1, 3000)])
        c.commit()
        c.execute("DELETE FROM urls WHERE id > 100")
        c.commit()
        c.close()
        res = carve_database(p, max_scan_bytes=500)
        self.assertTrue(res.stats["truncated"])
        self.assertTrue(any("limit" in w.lower() for w in res.warnings))
