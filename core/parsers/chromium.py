"""
Parsers for the Chromium family (Chrome, Edge, Brave, Opera). All three
artefact types (History, Login Data, Cookies, Downloads) share the same
SQLite schema across these browsers since they all fork from Chromium.

Every function takes a path that is ALREADY a safe temp copy opened
read-only (see core.utils.safe_copy_db / open_readonly) -- callers in
evidence/services.py handle that plumbing so parser code here stays
focused purely on schema.

NOTE: Chromium's schema has drifted slightly across versions. If a query
below fails against a given browser version, inspect the copied DB with
any SQLite browser to confirm column names before trusting the output
for real evidentiary work.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from core.utils import open_readonly

_CHROME_EPOCH = datetime(1601, 1, 1)


def _chrome_time_to_dt(value):
    if value in (None, 0, ""):
        return None
    try:
        return _CHROME_EPOCH + timedelta(microseconds=int(value))
    except (ValueError, OverflowError, OSError):
        return None


def parse_history(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT url, title, visit_count, last_visit_time FROM urls "
            "ORDER BY last_visit_time DESC"
        )
        rows = []
        for url, title, visit_count, last_visit_time in cur.fetchall():
            rows.append({
                "url": url or "",
                "title": title or "",
                "visit_count": visit_count or 0,
                "last_visit_time": _chrome_time_to_dt(last_visit_time),
            })
        return rows
    finally:
        conn.close()


def parse_logins(db_path) -> list[dict]:
    """Site + username metadata ONLY. password_value is ALWAYS the literal
    string 'Protected' -- this suite never decrypts or reads the real
    password_value column, by design, not just by UI masking."""
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT origin_url, username_value, date_created FROM logins "
            "ORDER BY date_created DESC"
        )
        rows = []
        for origin_url, username_value, date_created in cur.fetchall():
            rows.append({
                "site": origin_url or "",
                "username": username_value or "",
                "password_value": "Protected",
                "date_created": _chrome_time_to_dt(date_created),
            })
        return rows
    finally:
        conn.close()


def parse_cookies(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT host_key, name, path, expires_utc, is_secure, is_httponly, "
            "last_access_utc FROM cookies ORDER BY last_access_utc DESC"
        )
        rows = []
        for host_key, name, path, expires_utc, is_secure, is_httponly, last_access_utc in cur.fetchall():
            rows.append({
                "host": host_key or "",
                "name": name or "",
                "path": path or "",
                "expires_utc": _chrome_time_to_dt(expires_utc),
                "is_secure": bool(is_secure),
                "is_httponly": bool(is_httponly),
                "last_access_utc": _chrome_time_to_dt(last_access_utc),
                "value": "Protected",
            })
        return rows
    finally:
        conn.close()


_STATE_MAP = {0: "In progress", 1: "Complete", 2: "Cancelled", 3: "Interrupted", 4: "Interrupted"}
_DANGER_MAP = {0: "Not dangerous", 1: "Dangerous", 5: "Dangerous host", 6: "Potentially unwanted"}


def parse_downloads(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT target_path, tab_url, referrer, total_bytes, state, "
            "danger_type, start_time FROM downloads ORDER BY start_time DESC"
        )
        rows = []
        for target_path, tab_url, referrer, total_bytes, state, danger_type, start_time in cur.fetchall():
            rows.append({
                "target_path": target_path or "",
                "source_url": tab_url or "",
                "referrer": referrer or "",
                "total_bytes": total_bytes or 0,
                "state": _STATE_MAP.get(state, str(state)),
                "danger_type": _DANGER_MAP.get(danger_type, str(danger_type)),
                "start_time": _chrome_time_to_dt(start_time),
            })
        return rows
    finally:
        conn.close()
