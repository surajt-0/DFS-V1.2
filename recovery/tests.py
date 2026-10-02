"""End-to-end tests for deleted-data recovery, browser system-data recovery
and DNS details -- through the real API, the real upload pipeline and real
SQLite/WAL files (nothing is mocked except the machine's browser profile
discovery and DNS collection)."""
import json
import shutil
import sqlite3
import struct
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from billing.models import Plan
from core.browser_detect import DetectedProfile
from evidence.models import EvidenceItem
from recovery.models import DnsEntry, RecoveredRecord, StateItem

CH = datetime(1601, 1, 1)


def chrome_us(dt):
    return int((dt - CH).total_seconds() * 1_000_000)


def make_history(path, n=400, wal=False, evil_title=None):
    """Chromium-shaped History DB. secure_delete is OFF, like browsers that
    don't scrub (SQLite's own default varies by build)."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    c = sqlite3.connect(path)
    c.execute("PRAGMA secure_delete=OFF")
    if wal:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY AUTOINCREMENT,url LONGVARCHAR,title LONGVARCHAR,"
              "visit_count INTEGER DEFAULT 0 NOT NULL,typed_count INTEGER DEFAULT 0 NOT NULL,"
              "last_visit_time INTEGER NOT NULL,hidden INTEGER DEFAULT 0 NOT NULL)")
    c.execute("CREATE TABLE visits(id INTEGER PRIMARY KEY, url INTEGER NOT NULL, visit_time INTEGER NOT NULL)")
    base = datetime.utcnow() - timedelta(days=60)
    rows = []
    for i in range(1, n + 1):
        title = evil_title if (evil_title and i == 5) else f"Page {i} " + "x" * (i % 30)
        rows.append((i, f"https://host{i % 23}.example.org/p/{i}?k={i * 7}", title, 1 + i % 9, 0,
                     chrome_us(base + timedelta(minutes=9 * i)), 0))
    c.executemany("INSERT INTO urls VALUES (?,?,?,?,?,?,?)", rows)
    c.execute("INSERT INTO visits VALUES (1, 1, 1)")
    c.commit()
    return c, rows


def snss(urls):
    def cmd(cid, payload):
        return struct.pack("<H", len(payload) + 1) + bytes([cid]) + payload

    def nav(tab, idx, url, title):
        u, t = url.encode(), title.encode("utf-16-le")
        body = (struct.pack("<ii", tab, idx) + struct.pack("<I", len(u)) + u + b"\0" * ((4 - len(u) % 4) % 4)
                + struct.pack("<I", len(title)) + t + b"\0" * ((4 - len(t) % 4) % 4))
        return struct.pack("<I", len(body)) + body
    return b"SNSS" + struct.pack("<i", 3) + b"".join(cmd(6, nav(1, i, u, "T")) for i, u in enumerate(urls))


def bookmarks_json(urls):
    return json.dumps({"roots": {"bookmark_bar": {"type": "folder", "name": "Bar", "children": [
        {"type": "url", "name": u, "url": u, "date_added": "13340000000000000", "guid": u} for u in urls]}}})


@override_settings(EVIDENCE_STORAGE_ROOT=Path(tempfile.mkdtemp(prefix="dfs_test_ev_")))
class RecoveryEndToEnd(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_plans", verbosity=0)

    def _user(self, name, plan="pro"):
        c = APIClient()
        r = c.post("/api/accounts/signup/", {
            "username": name, "email": f"{name}@example.com", "password1": "Str0ng-Pass-123!",
            "password2": "Str0ng-Pass-123!", "organization": f"{name} org"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = get_user_model().objects.get(username=name)
        org = u.profile.org
        org.plan = Plan.objects.get(key=plan)
        org.save()
        return c

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dfs_test_src_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.c = self._user("alice")
        r = self.c.post("/api/cases/", {"name": "Case A"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.case = r.json()["id"]

    def upload(self, client, case, name, data, **extra):
        f = SimpleUploadedFile(name, data if isinstance(data, bytes) else data.encode())
        r = client.post(f"/api/evidence/case/{case}/upload/", {"file": f, **extra}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["results"][0]

    def upload_history_with_deletes(self, wal_companion=None):
        p = self.tmp / "History"
        c, rows = make_history(p, evil_title='=HYPERLINK("http://evil.example/","x")')
        c.execute("DELETE FROM urls WHERE id % 7 = 0")
        c.execute("DELETE FROM urls WHERE id BETWEEN 200 AND 260")
        c.commit()
        c.close()
        self.gone = [r for r in rows if r[0] % 7 == 0 or 200 <= r[0] <= 260]
        self.rows = rows
        res = self.upload(self.c, self.case, "History", p.read_bytes())
        return res

    # ------------------------------------------------------------------
    def test_carve_recovers_deleted_history_with_no_false_positives(self):
        res = self.upload_history_with_deletes()
        self.assertEqual(res["evidence_type"], "chromium_history")
        r = self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        out = r.json()["results"][0]
        self.assertIn(out["status"], ("ok", "partial"))
        self.assertGreater(out["records_found"], 0)

        got, page = [], 1
        while True:
            j = self.c.get(f"/api/recovery/case/{self.case}/deleted/?kind=history&page_size=200&page={page}").json()
            got += j["results"]
            if not j["next"]:
                break
            page += 1
        urls = {g["primary"] for g in got}
        gone = {r[1] for r in self.gone}
        alive = {r[1] for r in self.rows} - gone
        self.assertFalse(urls & alive, "a live (never-deleted) URL was reported as deleted")
        self.assertTrue(urls <= {r[1] for r in self.rows}, "recovered a URL that never existed")
        # SQLite overwrites some freed cells while rebalancing, so judge recall against what is
        # physically still in the evidence file: every such row must have been recovered.
        raw = Path(EvidenceItem.objects.get(case_id=self.case).stored_path).read_bytes()
        surviving = {r[1] for r in self.gone if r[1].encode() in raw}
        self.assertGreater(len(surviving), 30, "fixture should leave plenty of surviving remnants")
        self.assertEqual(surviving - urls, set(), "a row that is physically present was not recovered")
        for g in got:
            self.assertIn(g["confidence"], ("high", "medium", "low"))
            self.assertIn(g["source"], ("freelist_page", "freeblock", "wal", "wal_stale"))
        # confidence filter + sort both work
        hi = self.c.get(f"/api/recovery/case/{self.case}/deleted/?confidence=high&sort=-confidence").json()
        self.assertTrue(all(x["confidence"] == "high" for x in hi["results"]))

    def test_standard_history_table_is_unchanged_by_carving(self):
        self.upload_history_with_deletes()
        before = self.c.get(f"/api/evidence/case/{self.case}/table/history/").json()["count"]
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        after = self.c.get(f"/api/evidence/case/{self.case}/table/history/").json()["count"]
        self.assertEqual(before, after)
        self.assertEqual(before, len(self.rows) - len(self.gone))

    def test_original_evidence_file_is_never_modified(self):
        import hashlib
        res = self.upload_history_with_deletes()
        ev = EvidenceItem.objects.get(pk=res["id"])
        before = hashlib.sha256(Path(ev.stored_path).read_bytes()).hexdigest()
        self.assertEqual(before, ev.sha256)
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        self.c.post(f"/api/evidence/{ev.id}/reparse/")
        self.assertEqual(hashlib.sha256(Path(ev.stored_path).read_bytes()).hexdigest(), before)

    def test_csv_export_neutralises_formula_injection(self):
        self.upload_history_with_deletes()
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        resp = self.c.get(f"/recovery/case/{self.case}/deleted/?export=csv")
        self.assertEqual(resp.status_code, 200)
        text = resp.content.decode()
        self.assertNotIn(',=HYPERLINK', text)
        self.assertNotIn(',"=HYPERLINK', text)
        self.assertEqual(self.c.get(f"/recovery/case/{self.case}/deleted/?export=xml").status_code, 400)
        self.assertEqual(self.c.get(f"/recovery/case/{self.case}/nope/?export=csv").status_code, 400)

    def test_wal_companion_upload_is_used(self):
        p = self.tmp / "H"
        c, rows = make_history(p, n=300, wal=True)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("DELETE FROM urls WHERE id BETWEEN 100 AND 160")
        c.commit()
        shutil.copy(p, self.tmp / "History")
        shutil.copy(str(p) + "-wal", self.tmp / "History-wal")
        c.close()
        self.upload(self.c, self.case, "History", (self.tmp / "History").read_bytes())
        wal = self.upload(self.c, self.case, "History-wal", (self.tmp / "History-wal").read_bytes())
        self.assertEqual(wal["evidence_type"], "browser_state")   # companion is detected, not "other"
        r = self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json").json()["results"]
        hist = [x for x in r if x["filename"] == "History"][0]
        self.assertTrue(hist["wal_used"])
        self.assertGreaterEqual(hist["stats"]["deleted_in_wal"], 40)
        recs = RecoveredRecord.objects.filter(evidence__original_filename="History", source="wal")
        self.assertGreaterEqual(recs.count(), 40)

    def test_uploading_a_wal_mode_db_leaves_no_stray_files_beside_the_evidence(self):
        """Regression: content sniffing used to open the stored copy without
        immutable=1, which made SQLite drop empty -wal/-shm files next to it."""
        p = self.tmp / "H"
        c, _ = make_history(p, n=100, wal=True)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy(p, self.tmp / "History")
        c.close()
        res = self.upload(self.c, self.case, "History", (self.tmp / "History").read_bytes())
        stored = Path(EvidenceItem.objects.get(pk=res["id"]).stored_path)
        self.assertEqual([f.name for f in stored.parent.iterdir() if f.name.startswith(stored.name)], [stored.name])

    def test_carve_rejects_non_database_evidence_gracefully(self):
        self.upload(self.c, self.case, "Bookmarks", bookmarks_json(["https://a.example/"]))
        ev = EvidenceItem.objects.get(case_id=self.case)
        r = self.c.post(f"/api/recovery/case/{self.case}/carve/", {"evidence_id": ev.id}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"][0]["status"], "failed")
        garbage = self.upload(self.c, self.case, "History", b"SQLite format 3\x00" + b"\xff" * 5000)
        r = self.c.post(f"/api/recovery/case/{self.case}/carve/", {"evidence_id": garbage["id"]}, format="json")
        self.assertEqual(r.status_code, 200)   # a failed run is recorded; never a 500
        self.assertEqual(r.json()["results"][0]["status"], "failed")
        self.assertEqual(self.c.post(f"/api/recovery/case/{self.case}/carve/", {"evidence_id": "abc"},
                                     format="json").status_code, 400)

    # ------------------------------------------------------------------
    def test_system_data_detection_parsing_and_bookmark_diff(self):
        types = {
            "Bookmarks": bookmarks_json(["https://kept.example/"]),
            "Bookmarks.bak": bookmarks_json(["https://kept.example/", "https://removed.example/"]),
            "Current Session": snss(["https://open.example/a", "https://open.example/b"]),
            "Preferences": json.dumps({"dns_over_https": {"mode": "secure", "templates": "https://dns.example/q"},
                                       "profile": {"name": "P1"}}),
        }
        for name, data in types.items():
            res = self.upload(self.c, self.case, name, data)
            self.assertEqual(res["evidence_type"], "browser_state", name)
            self.assertFalse(res.get("parse_warning"), (name, res.get("parse_warning")))
        j = self.c.get(f"/api/recovery/case/{self.case}/state/?category=bookmark").json()
        status = {i["name"]: i["status"] for i in j["results"]}
        self.assertEqual(status["https://removed.example/"], "backup_only")
        self.assertEqual(status["https://kept.example/"], "present")
        sess = self.c.get(f"/api/recovery/case/{self.case}/state/?category=session").json()
        self.assertEqual({i["name"] for i in sess["results"]}, {"https://open.example/a", "https://open.example/b"})
        s = self.c.get(f"/api/recovery/case/{self.case}/summary/").json()
        self.assertEqual(s["counts"]["state"]["backup_only"], 1)
        self.assertEqual(set(s["file_access"]), {"csv", "xlsx", "json"})
        # re-parsing must replace, not duplicate, the rows
        ev = EvidenceItem.objects.get(case_id=self.case, original_filename="Bookmarks")
        n_before = StateItem.objects.filter(evidence=ev).count()
        self.assertEqual(self.c.post(f"/api/evidence/{ev.id}/reparse/").status_code, 200)
        self.assertEqual(StateItem.objects.filter(evidence=ev).count(), n_before)
        dns = self.c.get(f"/api/recovery/case/{self.case}/state/?dns=1").json()
        self.assertEqual([i["name"] for i in dns["results"]],
                         ["dns_over_https.mode", "dns_over_https.templates"])

    def test_firefox_closed_tabs_are_recovered(self):
        try:
            import lz4.block  # only used to build the fixture; not a runtime dependency
        except ImportError:
            self.skipTest("the 'lz4' package is needed to build this fixture")
        from core.recovery.mozlz4 import MAGIC
        doc = {"windows": [{"tabs": [{"entries": [{"url": "https://open.example/", "title": "o"}]}],
                            "_closedTabs": [{"closedAt": 1700000000000,
                                             "state": {"entries": [{"url": "https://closed.example/x", "title": "c"}]}}]}]}
        raw = json.dumps(doc).encode()
        data = MAGIC + struct.pack("<I", len(raw)) + lz4.block.compress(raw, store_size=False)
        res = self.upload(self.c, self.case, "recovery.jsonlz4", data)
        self.assertEqual(res["evidence_type"], "browser_state")
        j = self.c.get(f"/api/recovery/case/{self.case}/state/?status=recovered_closed").json()
        self.assertEqual([i["name"] for i in j["results"]], ["https://closed.example/x"])

    def test_corrupt_state_file_reports_parse_warning_not_500(self):
        res = self.upload(self.c, self.case, "Bookmarks", b"{ not json")
        self.assertEqual(res["evidence_type"], "browser_state")
        self.assertTrue(res.get("parse_warning"))

    # ------------------------------------------------------------------
    def test_dns_hosts_file_flags_and_uploaded_cache(self):
        hosts = ("127.0.0.1 localhost\n185.9.9.9 www.paypal.com\n0.0.0.0 update.microsoft.com\n"
                 "0.0.0.0 ads.example.net\n")
        res = self.upload(self.c, self.case, "hosts", hosts)
        self.assertEqual(res["evidence_type"], "dns_data")
        win = ("    x.example\n    ------\n    Record Name . . . . . : x.example\n    Record Type . . . . . : 1\n"
               "    Time To Live  . . . . : 30\n    Data Length . . . . . : 4\n    Section . . . . . . . : Answer\n"
               "    A (Host) Record . . . : 10.1.2.3\n\n")
        res = self.upload(self.c, self.case, "dnscache.txt", win)
        self.assertEqual(res["evidence_type"], "dns_data")
        j = self.c.get(f"/api/recovery/case/{self.case}/dns/entries/?severity=alert").json()
        self.assertEqual([e["name"] for e in j["results"]], ["www.paypal.com"])
        j = self.c.get(f"/api/recovery/case/{self.case}/dns/entries/?type=cache").json()
        self.assertEqual((j["results"][0]["name"], j["results"][0]["value"], j["results"][0]["ttl"]),
                         ("x.example", "10.1.2.3", 30))
        self.assertEqual(self.c.get(f"/api/recovery/case/{self.case}/summary/").json()["counts"]["dns"]["alerts"], 1)

    def test_domains_include_recovered_only_hosts(self):
        self.upload_history_with_deletes()
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        j = self.c.get(f"/api/recovery/case/{self.case}/dns/domains/?page_size=200").json()
        self.assertGreater(j["count"], 0)
        d = j["results"][0]
        self.assertTrue({"domain", "registrable", "sources", "live", "recovered", "only_in_recovered"} <= set(d))
        # every host in this fixture is also live in remaining rows -> none are recovered-only
        self.assertEqual(self.c.get(f"/api/recovery/case/{self.case}/dns/domains/?only_recovered=1").json()["count"], 0)
        csv = self.c.get(f"/recovery/case/{self.case}/domains/?export=csv")
        self.assertEqual(csv.status_code, 200)

    def test_lookup_requires_confirmation_and_valid_hostnames(self):
        url = f"/api/recovery/case/{self.case}/dns/lookup/"
        self.assertEqual(self.c.post(url, {"domains": ["localhost"]}, format="json").status_code, 400)
        self.assertEqual(self.c.post(url, {"domains": "localhost", "confirm": True}, format="json").status_code, 400)
        r = self.c.post(url, {"domains": ["localhost", "not a host!", "http://x/y", "127.0.0.1"],
                              "confirm": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        j = r.json()
        self.assertEqual(j["looked_up"], 1)
        self.assertEqual(len(j["invalid"]), 3)
        self.assertTrue(DnsEntry.objects.filter(case_id=self.case, origin="active_lookup", name="localhost").exists())
        self.assertEqual(self.c.post(f"/api/recovery/case/{self.case}/dns/clear-lookups/").json()["removed"] >= 1, True)

    def test_local_dns_scan_is_deployment_gated(self):
        url = f"/api/recovery/case/{self.case}/dns/scan-local/"
        self.assertEqual(self.c.post(url).status_code, 403)
        with override_settings(ENABLE_LOCAL_BROWSER_SCAN=True):
            r = self.c.post(url)
            self.assertEqual(r.status_code, 200, r.content)
            self.assertIn("platform", r.json())

    # ------------------------------------------------------------------
    def test_free_plan_and_other_tenants_are_locked_out(self):
        self.upload_history_with_deletes()
        free = self._user("freddy", plan="free")
        # different organization => cannot even see the case
        for path in ("summary/", "deleted/", "state/", "dns/entries/", "dns/domains/"):
            self.assertEqual(free.get(f"/api/recovery/case/{self.case}/{path}").status_code, 403, path)
        self.assertEqual(free.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json").status_code, 403)
        self.assertEqual(free.get(f"/recovery/case/{self.case}/deleted/?export=csv").status_code, 403)
        # own case on the Free plan: view-only, feature off -> 402 (plan), not 403 (role)
        # (Free can't create cases via the API, so make one directly.)
        from cases.models import Case
        u = get_user_model().objects.get(username="freddy")
        fc = Case.objects.create(name="F", investigator=u, organization=u.profile.org)
        self.assertEqual(free.get(f"/api/recovery/case/{fc.pk}/deleted/").status_code, 402)
        self.assertEqual(free.post(f"/api/recovery/case/{fc.pk}/carve/", {}, format="json").status_code, 402)
        s = free.get(f"/api/recovery/case/{fc.pk}/summary/").json()
        self.assertEqual(s["enabled"], {"data_recovery": False, "dns_details": False})
        self.assertFalse(s["can_run"])
        # unauthenticated
        self.assertIn(APIClient().get(f"/api/recovery/case/{self.case}/summary/").status_code, (401, 403))
        self.assertEqual(APIClient().get(f"/recovery/case/{self.case}/deleted/?export=csv").status_code, 401)

    def test_disabling_the_plan_flag_blocks_existing_results(self):
        self.upload_history_with_deletes()
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        Plan.objects.filter(key="pro").update(feature_data_recovery=False)
        self.assertEqual(self.c.get(f"/api/recovery/case/{self.case}/deleted/").status_code, 402)

    # ------------------------------------------------------------------
    def test_local_scan_captures_wal_and_optional_system_data(self):
        prof = self.tmp / "Default"
        prof.mkdir()
        c, rows = make_history(prof / "History", n=300, wal=True)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("DELETE FROM urls WHERE id BETWEEN 100 AND 160")
        c.commit()
        # simulate "browser still running": keep the connection (and WAL) alive while we scan
        (prof / "Bookmarks").write_text(bookmarks_json(["https://b.example/"]))
        dp = DetectedProfile(browser="Chrome", profile_name="Default", history_path=prof / "History",
                             state_paths=[prof / "Bookmarks"])
        with override_settings(ENABLE_LOCAL_BROWSER_SCAN=True), mock.patch("evidence.api.detect_all", return_value=[dp]):
            plain = self.c.post(f"/api/evidence/case/{self.case}/scan-local/", {}, format="json")
            self.assertEqual(plain.status_code, 201, plain.content)
            self.assertEqual([r["original_filename"] for r in plain.json()["results"]], ["History"])
            self.assertIn("WAL companion captured", plain.json()["results"][0].get("note", "") or
                          EvidenceItem.objects.get(pk=plain.json()["results"][0]["id"]).note)
            full = self.c.post(f"/api/evidence/case/{self.case}/scan-local/", {"include_system_data": True}, format="json")
            self.assertEqual(sorted(r["original_filename"] for r in full.json()["results"]), ["Bookmarks", "History"])
        c.close()
        r = self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json").json()["results"]
        self.assertTrue(all(x["wal_used"] for x in r))
        self.assertGreaterEqual(sum(x["stats"]["deleted_in_wal"] for x in r), 40)

    def test_system_data_scan_requires_the_plan_feature(self):
        Plan.objects.filter(key="pro").update(feature_data_recovery=False)
        with override_settings(ENABLE_LOCAL_BROWSER_SCAN=True), mock.patch("evidence.api.detect_all", return_value=[]):
            r = self.c.post(f"/api/evidence/case/{self.case}/scan-local/", {"include_system_data": True}, format="json")
            self.assertEqual(r.status_code, 402)

    # ------------------------------------------------------------------
    def test_pdf_report_includes_recovery_section_and_reparse_delete_cascade(self):
        res = self.upload_history_with_deletes()
        self.c.post(f"/api/recovery/case/{self.case}/carve/", {}, format="json")
        self.upload(self.c, self.case, "hosts", "185.9.9.9 www.paypal.com\n")
        pdf = self.c.get(f"/api/cases/{self.case}/report/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.c.delete(f"/api/evidence/{res['id']}/").status_code, 204)
        self.assertFalse(RecoveredRecord.objects.filter(evidence_id=res["id"]).exists())

    def test_demo_case_and_existing_flows_still_work(self):
        r = self.c.post("/api/evidence/demo-case/")
        self.assertEqual(r.status_code, 201)
        demo = r.json()["id"]
        self.assertEqual(self.c.get(f"/api/recovery/case/{demo}/summary/").status_code, 200)
        # demo evidence has no file behind it -> carve reports failure cleanly
        r = self.c.post(f"/api/recovery/case/{demo}/carve/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(x["status"] == "failed" for x in r.json()["results"]))
        self.assertEqual(self.c.get(f"/api/evidence/case/{demo}/table/history/").status_code, 200)
