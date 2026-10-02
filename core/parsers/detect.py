"""Auto-detects which browser artifact an uploaded file is, so a batch
upload (evidence/api.py's EvidenceUploadAPI) doesn't require the examiner
to manually classify each file first.

Detection order: cheap filename hints first (these are the literal on-disk
names every major browser actually uses -- "History", "Login Data",
"Cookies", "places.sqlite", "logins.json", "cookies.sqlite"), then content
sniffing as the reliable fallback for renamed files (e.g. someone exported
"History" as "History_2026.sqlite" during collection). Content sniffing is
also what disambiguates Chromium's History (tables: urls, visits, downloads)
from Safari's History.db (tables: history_items, history_visits) -- same
filename convention, different browsers, different schemas.

Returns None (never guesses) when nothing matches -- callers fall back to
EvidenceType.OTHER and leave the file unparsed for manual classification
rather than mis-filing it under the wrong parser.
"""
from __future__ import annotations
import json
import sqlite3
import zipfile
from pathlib import Path


def _sqlite_tables(path) -> set[str] | None:
    """Table names in a SQLite file, or None if it isn't one (or can't be
    read) -- never raises, since this is a best-effort probe over
    arbitrary user-uploaded bytes."""
    try:
        # immutable=1: never let SQLite create -wal/-shm files beside the evidence
        # (a plain read-only open of a WAL-mode DB does exactly that), and never
        # look at a -wal file -- table names live in the main file anyway.
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        return None
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cur.fetchall()}
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _looks_like_dns_text(path) -> bool:
    """Cheap content sniff for text exports of the DNS cache / resolver
    config (ipconfig /displaydns, scutil --dns, resolvectl status,
    resolv.conf). Reads only the first 64 KB and never raises."""
    import re
    try:
        with open(path, "rb") as fh:
            head = fh.read(65536)
    except OSError:
        return False
    if b"\x00" in head[:4096]:
        return False   # binary (e.g. SQLite) -- not a text export
    text = head.decode("utf-8", "ignore")
    return bool(
        re.search(r"Record Name\s*[. ]*:", text)
        or re.search(r"^resolver #\d+", text, re.M)
        or re.search(r"^\s*nameserver\s+\S+", text, re.M)
        or (re.search(r"^(Global|Link \d+ \()", text, re.M) and "DNS Server" in text)
    )


def detect_evidence_type(file_path, original_filename: str):
    """Returns an EvidenceItem.EvidenceType value, or None if undetermined.
    Imports EvidenceItem lazily to avoid a circular import (this module is
    imported by evidence/services.py, which models.py doesn't depend on,
    but keeping parsers free of app-model imports at module load time is
    the existing convention in core/parsers/*)."""
    from evidence.models import EvidenceItem
    T = EvidenceItem.EvidenceType

    name = (original_filename or "").strip().lower()
    ext = Path(name).suffix

    # --- Fast filename hints -- the real on-disk names these browsers use.
    if ext == ".zip":
        return T.CACHE_ARCHIVE
    if name == "places.sqlite":
        return T.FIREFOX_HISTORY
    if name == "cookies.sqlite":
        return T.FIREFOX_COOKIES
    if name == "logins.json":
        return T.FIREFOX_LOGINS
    if name in ("login data", "login data.db", "login data.sqlite"):
        return T.CHROMIUM_LOGINS
    if name == "cookies":
        return T.CHROMIUM_COOKIES

    # --- Browser system data (sessions, bookmarks, prefs, WAL companions...) and DNS data.
    from core.recovery.browser_state import classify_state_file
    if classify_state_file(name):
        return T.BROWSER_STATE
    if name in ("hosts", "resolv.conf"):
        return T.DNS_DATA
    if ext in ("", ".txt", ".log", ".conf", ".dns"):
        if _looks_like_dns_text(file_path):
            return T.DNS_DATA

    # --- JSON sniff (covers logins.json even if the examiner renamed it).
    if ext in ("", ".json"):
        try:
            data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            if isinstance(data, dict) and "logins" in data:
                return T.FIREFOX_LOGINS
        except (OSError, ValueError, UnicodeDecodeError):
            pass

    # --- SQLite content sniff -- reliable fallback, and what disambiguates
    # Chromium's "History" from Safari's identically-named "History.db".
    tables = _sqlite_tables(file_path)
    if tables:
        if {"urls", "visits"} <= tables:
            return T.CHROMIUM_HISTORY
        if {"history_items", "history_visits"} <= tables:
            return T.SAFARI_HISTORY
        if "moz_places" in tables:
            return T.FIREFOX_HISTORY
        if "moz_cookies" in tables:
            return T.FIREFOX_COOKIES
        if "logins" in tables:
            return T.CHROMIUM_LOGINS
        if "cookies" in tables:
            return T.CHROMIUM_COOKIES

    return None
