"""
Dispatches an EvidenceItem to the right parser (core.parsers.*) and bulk
loads the results into the normalized *Entry tables. Every parser call
happens against a safe temp copy (core.utils.safe_copy_db) that is deleted
again immediately after -- the original uploaded evidence file is never
reopened for writing and is left byte-for-byte untouched.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime as _dt, timezone as _tz
from django.utils import timezone

from core.parsers import cache as p_cache
from core.parsers import chromium as p_chromium
from core.parsers import firefox as p_firefox
from core.parsers import safari as p_safari
from core.utils import cleanup_dir, safe_copy_db

from .models import (
    CacheEntry, CookieEntry, DownloadEntry, EvidenceItem, HistoryEntry, LoginEntry,
)

BATCH_SIZE = 500


class ParseError(Exception):
    pass


def _aware(row: dict) -> dict:
    """Every parser/demo-data row may carry naive datetimes (they come from
    epoch-math, not Django) -- make them timezone-aware (UTC) here, once,
    centrally, rather than in every parser."""
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, _dt) and timezone.is_naive(v):
            out[k] = timezone.make_aware(v, _tz.utc)
    return out


def _bulk(model, rows):
    if rows:
        model.objects.bulk_create(rows, batch_size=BATCH_SIZE)
    return len(rows)


def parse_evidence(evidence: EvidenceItem) -> int:
    """Runs the appropriate parser for evidence.evidence_type, stores
    normalized rows, and updates status/row_count/parsed_at. Returns the
    number of rows parsed. Raises ParseError on failure (caller marks the
    EvidenceItem as failed and stores parse_error)."""
    t = EvidenceItem.EvidenceType
    etype = evidence.evidence_type
    work_dir = None
    try:
        # Clear any previous parse (re-parse support)
        _clear_existing(evidence)

        if etype == t.BROWSER_STATE:
            from recovery.services import RecoveryError, parse_state_evidence
            try:
                count = parse_state_evidence(evidence)
            except RecoveryError as exc:
                raise ParseError(str(exc)) from exc
        elif etype == t.DNS_DATA:
            from recovery.services import RecoveryError, parse_dns_evidence
            try:
                count = parse_dns_evidence(evidence)
            except RecoveryError as exc:
                raise ParseError(str(exc)) from exc
        elif etype == t.CACHE_ARCHIVE:
            rows = p_cache.scan_cache_zip(evidence.stored_path)
            count = _bulk(CacheEntry, [
                CacheEntry(evidence=evidence, **_aware(row)) for row in rows
            ])
        elif etype == t.FIREFOX_LOGINS:
            rows = p_firefox.parse_logins(evidence.stored_path)
            count = _bulk(LoginEntry, [LoginEntry(evidence=evidence, **_aware(row)) for row in rows])
        else:
            # Everything else is a SQLite file -> safe copy, then parse.
            safe_path = safe_copy_db(evidence.stored_path)
            work_dir = safe_path.parent
            if etype == t.CHROMIUM_HISTORY:
                rows = p_chromium.parse_history(safe_path)
                count = _bulk(HistoryEntry, [HistoryEntry(evidence=evidence, **_aware(row)) for row in rows])
                # Chrome/Edge/Brave/Opera's History file also contains a
                # `downloads` table -- surface it from the SAME upload
                # instead of making the examiner upload the same file again
                # under a different declared type.
                try:
                    dl_rows = p_chromium.parse_downloads(safe_path)
                    count += _bulk(
                        DownloadEntry, [DownloadEntry(evidence=evidence, **_aware(row)) for row in dl_rows]
                    )
                except sqlite3.Error:
                    pass  # older/partial copies may lack a downloads table; history still succeeded
            elif etype == t.CHROMIUM_LOGINS:
                rows = p_chromium.parse_logins(safe_path)
                count = _bulk(LoginEntry, [LoginEntry(evidence=evidence, **_aware(row)) for row in rows])
            elif etype == t.CHROMIUM_COOKIES:
                rows = p_chromium.parse_cookies(safe_path)
                count = _bulk(CookieEntry, [CookieEntry(evidence=evidence, **_aware(row)) for row in rows])
            elif etype == t.CHROMIUM_DOWNLOADS:
                rows = p_chromium.parse_downloads(safe_path)
                count = _bulk(DownloadEntry, [DownloadEntry(evidence=evidence, **_aware(row)) for row in rows])
            elif etype == t.FIREFOX_HISTORY:
                rows = p_firefox.parse_history(safe_path)
                count = _bulk(HistoryEntry, [HistoryEntry(evidence=evidence, **_aware(row)) for row in rows])
            elif etype == t.FIREFOX_COOKIES:
                rows = p_firefox.parse_cookies(safe_path)
                count = _bulk(CookieEntry, [CookieEntry(evidence=evidence, **_aware(row)) for row in rows])
            elif etype == t.SAFARI_HISTORY:
                rows = p_safari.parse_history(safe_path)
                count = _bulk(HistoryEntry, [HistoryEntry(evidence=evidence, **_aware(row)) for row in rows])
            else:
                raise ParseError(f"No parser registered for evidence type '{etype}'.")

        evidence.status = EvidenceItem.Status.PARSED
        evidence.row_count = count
        evidence.parse_error = ""
        evidence.parsed_at = timezone.now()
        evidence.save(update_fields=["status", "row_count", "parse_error", "parsed_at"])
        return count
    except Exception as exc:
        evidence.status = EvidenceItem.Status.FAILED
        evidence.parse_error = str(exc)
        evidence.save(update_fields=["status", "parse_error"])
        raise ParseError(str(exc)) from exc
    finally:
        if work_dir is not None:
            cleanup_dir(work_dir)


def _clear_existing(evidence: EvidenceItem):
    evidence.history_entries.all().delete()
    evidence.login_entries.all().delete()
    evidence.cookie_entries.all().delete()
    evidence.download_entries.all().delete()
    evidence.cache_entries.all().delete()
    # System-data / DNS rows are rebuilt by their own parse step. Carved
    # (deleted-data) results are deliberately NOT cleared here: they come
    # from a separate, examiner-triggered run and survive a plain re-parse.
    evidence.state_items.all().delete()
    evidence.dns_entries.all().delete()


def load_demo_data(evidence: EvidenceItem) -> int:
    """Populate an evidence item with synthetic demo rows (no real parsing,
    no real file needed) -- used by the one-click Demo Case feature."""
    from core.parsers import demo_data as dd
    t = EvidenceItem.EvidenceType
    _clear_existing(evidence)
    etype = evidence.evidence_type
    if etype in (t.CHROMIUM_HISTORY, t.FIREFOX_HISTORY, t.SAFARI_HISTORY):
        count = _bulk(HistoryEntry, [HistoryEntry(evidence=evidence, **_aware(row)) for row in dd.demo_history()])
    elif etype in (t.CHROMIUM_LOGINS, t.FIREFOX_LOGINS):
        count = _bulk(LoginEntry, [LoginEntry(evidence=evidence, **_aware(row)) for row in dd.demo_logins()])
    elif etype in (t.CHROMIUM_COOKIES, t.FIREFOX_COOKIES):
        count = _bulk(CookieEntry, [CookieEntry(evidence=evidence, **_aware(row)) for row in dd.demo_cookies()])
    elif etype == t.CHROMIUM_DOWNLOADS:
        count = _bulk(DownloadEntry, [DownloadEntry(evidence=evidence, **_aware(row)) for row in dd.demo_downloads()])
    elif etype == t.CACHE_ARCHIVE:
        count = _bulk(CacheEntry, [CacheEntry(evidence=evidence, **_aware(row)) for row in dd.demo_cache()])
    else:
        count = 0
    evidence.status = EvidenceItem.Status.PARSED
    evidence.row_count = count
    evidence.parsed_at = timezone.now()
    evidence.save(update_fields=["status", "row_count", "parsed_at"])
    return count
