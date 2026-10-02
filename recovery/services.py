"""Glue between the pure engines (core.recovery, core.dnsintel) and the
Django models. Every engine call runs against a safe working COPY that is
deleted afterwards -- stored evidence files are never opened for writing.
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import datetime, timezone as _tz
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from core.dnsintel import domains as dom
from core.dnsintel import hosts as hosts_mod
from core.dnsintel import lookup as lookup_mod
from core.dnsintel import resolver as resolver_mod
from core.recovery import browser_state as bs
from core.recovery.sqlite_carver import CarveError, carve_database
from core.utils import cleanup_dir, working_copy_dir
from evidence.models import CookieEntry, DownloadEntry, EvidenceItem, HistoryEntry, LoginEntry

from .models import DnsEntry, RecoveredRecord, RecoveryRun, StateItem

T = EvidenceItem.EvidenceType
BATCH = 500
MAX_TEXT_BYTES = 32 * 1024 * 1024
MAX_LOOKUP_DOMAINS = 25

# Evidence types whose file is a SQLite DB with tables the carver understands.
CARVABLE_TYPES = {
    T.CHROMIUM_HISTORY, T.CHROMIUM_DOWNLOADS, T.CHROMIUM_COOKIES, T.CHROMIUM_LOGINS,
    T.FIREFOX_HISTORY, T.FIREFOX_COOKIES,
}


class RecoveryError(Exception):
    pass


def _aware(dt):
    if dt is not None and timezone.is_naive(dt):
        return timezone.make_aware(dt, _tz.utc)
    return dt


def _bulk(model, objs):
    if objs:
        model.objects.bulk_create(objs, batch_size=BATCH)
    return len(objs)


# ---------------------------------------------------------------------------
# Deleted-data carving
# ---------------------------------------------------------------------------
def _is_wal(path: Path) -> bool:
    """A real, non-empty SQLite WAL (magic 0x377f0682/3). Guards against empty
    stub files and against picking up something that merely has the right name."""
    try:
        if path.stat().st_size <= 32:
            return False
        with open(path, "rb") as fh:
            return fh.read(4) in (b"\x37\x7f\x06\x82", b"\x37\x7f\x06\x83")
    except OSError:
        return False


def companion_wal_path(evidence: EvidenceItem):
    """Path of a -wal file belonging to this DB evidence, if one was captured
    (next to the stored copy by the local scan, or uploaded separately as
    '<name>-wal' into the same case)."""
    if evidence.stored_path:
        sib = Path(str(evidence.stored_path) + "-wal")
        if _is_wal(sib):
            return sib
    wal_name = (evidence.original_filename + "-wal").lower()
    for other in evidence.case.evidence_items.exclude(pk=evidence.pk):
        if other.original_filename.lower() == wal_name and other.stored_path and _is_wal(Path(other.stored_path)):
            return Path(other.stored_path)
    return None


def carve_evidence(evidence: EvidenceItem, user) -> RecoveryRun:
    """Run the carver on one evidence item; replaces any previous carve
    results for that item. Never raises for an ordinary unreadable/unsupported
    file -- a FAILED run is recorded instead so the examiner sees why."""
    run = RecoveryRun(case=evidence.case, evidence=evidence, created_by=user)
    if evidence.evidence_type not in CARVABLE_TYPES:
        run.status, run.error = RecoveryRun.Status.FAILED, (
            "Deleted-record recovery applies to browser SQLite databases (History, Cookies, Login Data, "
            "places.sqlite, cookies.sqlite). This evidence type isn't one."
        )
        run.save()
        return run
    if not evidence.stored_path or not Path(evidence.stored_path).exists():
        run.status, run.error = RecoveryRun.Status.FAILED, "The stored evidence file isn't available on disk."
        run.save()
        return run

    work_dir = working_copy_dir()
    try:
        copy = work_dir / Path(evidence.stored_path).name
        shutil.copy2(evidence.stored_path, copy)
        wal_src = companion_wal_path(evidence)
        wal_copy = None
        if wal_src:
            wal_copy = work_dir / (copy.name + "-wal")
            shutil.copy2(wal_src, wal_copy)
        try:
            result = carve_database(copy, wal_copy)
        except CarveError as exc:
            run.status, run.error = RecoveryRun.Status.FAILED, str(exc)
            run.wal_used = bool(wal_src)
            run.save()
            return run

        warnings = list(result.warnings)
        if "sqlite-snapshot" in (evidence.note or ""):
            warnings.append(
                "This evidence was copied with SQLite's snapshot fallback (the browser had the file locked). "
                "A snapshot contains only live rows, so deleted remnants are normally NOT present in it. "
                "Close the browser and re-collect the file for a meaningful recovery attempt."
            )
        if not result.records and not warnings:
            warnings.append(
                "No deleted remnants were found. That can mean nothing was deleted, the browser uses "
                "secure_delete, the database was VACUUMed, or the freed space was overwritten by later writes."
            )
        with transaction.atomic():
            RecoveredRecord.objects.filter(evidence=evidence).delete()
            run.records_found = len(result.records)
            run.stats = result.stats
            run.warnings = warnings
            run.wal_used = bool(wal_src)
            run.status = RecoveryRun.Status.PARTIAL if (warnings and result.records) or result.stats.get("truncated") \
                else RecoveryRun.Status.OK
            run.save()
            _bulk(RecoveredRecord, [
                RecoveredRecord(
                    evidence=evidence, run=run, kind=r.kind, browser=r.browser, table_name=r.table,
                    source=r.source, confidence=r.confidence, status=r.status,
                    primary=r.primary[:8192], secondary=(r.secondary or "")[:8192],
                    event_time=_aware(r.event_time), detail=r.detail,
                    page_no=r.page_no, offset=r.offset, rowid=r.rowid,
                ) for r in result.records
            ])
        return run
    except OSError as exc:
        run.status, run.error = RecoveryRun.Status.FAILED, f"Couldn't prepare a working copy ({exc})."
        run.save()
        return run
    finally:
        cleanup_dir(work_dir)


def carvable_evidence(case):
    return [e for e in case.evidence_items.all() if e.evidence_type in CARVABLE_TYPES]


# ---------------------------------------------------------------------------
# Browser system data
# ---------------------------------------------------------------------------
def _refresh_bookmark_status(case):
    """Bookmarks present in a backup but absent from the reference copy are
    the ones the user deleted since that backup."""
    items = list(StateItem.objects.filter(evidence__case=case, category=bs.CAT_BOOKMARK)
                 .select_related("evidence"))
    # Compare like with like: same browser AND same profile. The local scan
    # labels each evidence note "Auto-detected: <Browser> (<profile>) [...]";
    # for manual uploads the examiner's own note plays the same grouping role.
    by_browser = defaultdict(list)
    for it in items:
        by_browser[(it.browser, (it.evidence.note or "").split(" [")[0])].append(it)
    changed = []
    for (browser, _profile), group in by_browser.items():
        if browser == "chromium":
            ref_src = {i.source_file for i in group if i.source_file.lower() == "bookmarks"}
        else:
            srcs = sorted({i.source_file for i in group})
            ref_src = {srcs[-1]} if srcs else set()   # newest dated backup
        if not ref_src:
            continue
        ref_urls = {i.name for i in group if i.source_file in ref_src}
        for i in group:
            want = "present" if i.source_file in ref_src or i.name in ref_urls else "backup_only"
            if i.status != want:
                i.status = want
                changed.append(i)
    if changed:
        StateItem.objects.bulk_update(changed, ["status"], batch_size=BATCH)


def parse_state_evidence(evidence: EvidenceItem) -> int:
    try:
        items = bs.parse_state_file(evidence.stored_path, evidence.original_filename)
    except bs.StateError as exc:
        raise RecoveryError(str(exc)) from exc
    StateItem.objects.filter(evidence=evidence).delete()
    n = _bulk(StateItem, [
        StateItem(evidence=evidence, category=i.category, browser=i.browser, name=i.name[:8192],
                  value=i.value[:2000], timestamp=_aware(i.timestamp), status=i.status,
                  source_file=i.source_file[:255], detail=i.detail)
        for i in items
    ])
    if any(i.category == bs.CAT_BOOKMARK for i in items):
        _refresh_bookmark_status(evidence.case)
    return n


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------
def _dns_rows_from_hosts(text):
    return [dict(entry_type="hosts", name=e.hostname, value=e.ip, flag=e.flag, severity=e.severity,
                 detail={"line": e.line_no, "comment": e.comment}) for e in hosts_mod.parse_hosts(text)]


def _dns_rows_from_engine(rows):
    return [dict(entry_type=r.entry_type, name=r.name, value=r.value, record_type=r.record_type,
                 ttl=r.ttl, detail=r.detail) for r in rows]


def _store_dns(case, evidence, origin, rows):
    return _bulk(DnsEntry, [
        DnsEntry(case=case, evidence=evidence, origin=origin, entry_type=r["entry_type"],
                 name=(r["name"] or "")[:2000], value=(r.get("value") or "")[:2000],
                 record_type=r.get("record_type", ""), ttl=r.get("ttl"), flag=r.get("flag", ""),
                 severity=r.get("severity", ""), detail=r.get("detail") or {})
        for r in rows
    ])


def parse_dns_evidence(evidence: EvidenceItem) -> int:
    p = Path(evidence.stored_path)
    try:
        if p.stat().st_size > MAX_TEXT_BYTES:
            raise RecoveryError("DNS file is too large to parse safely.")
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RecoveryError(f"Couldn't read the file ({exc}).") from exc
    name = evidence.original_filename.lower()
    rows = []
    if name == "hosts":
        rows = _dns_rows_from_hosts(text)
    else:
        rows = _dns_rows_from_engine(resolver_mod.sniff_and_parse(text))
        if not rows:
            rows = _dns_rows_from_hosts(text)   # last resort: hosts-style lines
    if not rows:
        raise RecoveryError("No DNS records, resolver settings or hosts entries were recognised in this file.")
    DnsEntry.objects.filter(evidence=evidence).delete()
    return _store_dns(evidence.case, evidence, DnsEntry.Origin.UPLOADED, rows)


def scan_local_dns(case) -> dict:
    """Collect DNS cache / resolver config / hosts file from THIS machine."""
    got = resolver_mod.collect_local()
    rows = _dns_rows_from_engine(got["rows"]) + _dns_rows_from_hosts(got["hosts_text"])
    with transaction.atomic():
        DnsEntry.objects.filter(case=case, origin=DnsEntry.Origin.LOCAL).delete()
        n = _store_dns(case, None, DnsEntry.Origin.LOCAL, rows)
    return {"platform": got["platform"], "stored": n, "notes": got["notes"]}


def run_lookups(case, names) -> dict:
    """Active lookups (explicit examiner request only)."""
    from concurrent.futures import ThreadPoolExecutor
    clean, seen = [], set()
    for n in names:
        n = (n or "").strip().lower().rstrip(".")
        if n and n not in seen:
            seen.add(n)
            clean.append(n)
    invalid = [n for n in clean if not dom.is_valid_hostname(n)]
    clean = [n for n in clean if dom.is_valid_hostname(n)][:MAX_LOOKUP_DOMAINS]
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lookup_mod.lookup_domain, clean))
    rows, failed = [], []
    for r in results:
        if r.error:
            failed.append({"name": r.name, "error": r.error})
        for rec in r.records:
            rows.append(dict(entry_type="lookup", name=rec.name, value=rec.value,
                             record_type=rec.record_type, ttl=rec.ttl))
    n = _store_dns(case, None, DnsEntry.Origin.LOOKUP, rows)
    return {"looked_up": len(clean), "records": n, "failed": failed, "invalid": invalid,
            "capped_at": MAX_LOOKUP_DOMAINS, "dnspython": lookup_mod.HAVE_DNSPYTHON}


def case_domains(case, *, q="", only_recovered=False) -> list:
    """Every host the case's data mentions, with where it was seen. Built
    from parsed tables, recovered (deleted) records and system data."""
    agg = {}

    def add(host, source, when=None, recovered=False):
        if not host:
            return
        e = agg.get(host)
        if e is None:
            e = agg[host] = {"domain": host, "registrable": dom.registrable(host), "is_ip": dom.is_ip(host),
                             "sources": defaultdict(int), "first_seen": None, "last_seen": None,
                             "live": 0, "recovered": 0}
        e["sources"][source] += 1
        e["recovered" if recovered else "live"] += 1
        if when:
            if e["first_seen"] is None or when < e["first_seen"]:
                e["first_seen"] = when
            if e["last_seen"] is None or when > e["last_seen"]:
                e["last_seen"] = when

    for url, t in HistoryEntry.objects.filter(evidence__case=case).values_list("url", "last_visit_time").iterator(2000):
        add(dom.host_of(url), "history", t)
    for url, ref, t in DownloadEntry.objects.filter(evidence__case=case).values_list(
            "source_url", "referrer", "start_time").iterator(2000):
        add(dom.host_of(url), "downloads", t)
        add(dom.host_of(ref), "downloads", t)
    for host, t in CookieEntry.objects.filter(evidence__case=case).values_list("host", "last_access_utc").iterator(2000):
        add(dom.host_from_cookie_domain(host), "cookies", t)
    for site, t in LoginEntry.objects.filter(evidence__case=case).values_list("site", "date_created").iterator(2000):
        add(dom.host_of(site), "logins", t)
    for cat, name, ts in StateItem.objects.filter(evidence__case=case,
                                                  category__in=["session", "bookmark", "network"]
                                                  ).values_list("category", "name", "timestamp").iterator(2000):
        add(dom.host_of(name), {"session": "sessions", "bookmark": "bookmarks", "network": "network state"}[cat], ts)
    for kind, primary, sec, t in RecoveredRecord.objects.filter(evidence__case=case).values_list(
            "kind", "primary", "secondary", "event_time").iterator(2000):
        if kind == "cookie":
            add(dom.host_from_cookie_domain(primary), "recovered cookies", t, True)
        elif kind == "download":
            add(dom.host_of(sec), "recovered downloads", t, True)
        else:
            add(dom.host_of(primary), f"recovered {kind}s" if kind != "history" else "recovered history", t, True)

    out = []
    ql = (q or "").strip().lower()
    for e in agg.values():
        e["sources"] = dict(e["sources"])
        e["total"] = e["live"] + e["recovered"]
        e["only_in_recovered"] = e["live"] == 0 and e["recovered"] > 0
        if ql and ql not in e["domain"]:
            continue
        if only_recovered and not e["only_in_recovered"]:
            continue
        out.append(e)
    out.sort(key=lambda e: (-e["total"], e["domain"]))
    return out
