"""
Parsers for Firefox artefacts: places.sqlite (history + downloads via
moz_annos), logins.json (saved logins -- metadata only, password always
masked), cookies.sqlite.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path

from core.utils import open_readonly

_UNIX_EPOCH = datetime(1970, 1, 1)


def _micros_to_dt(value):
    if value in (None, 0, ""):
        return None
    try:
        return _UNIX_EPOCH + timedelta(microseconds=int(value))
    except (ValueError, OverflowError, OSError):
        return None


def _seconds_to_dt(value):
    if value in (None, 0, ""):
        return None
    try:
        return datetime.utcfromtimestamp(int(value))
    except (ValueError, OverflowError, OSError):
        return None


def parse_history(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT url, title, visit_count, last_visit_date FROM moz_places "
            "WHERE last_visit_date IS NOT NULL ORDER BY last_visit_date DESC"
        )
        rows = []
        for url, title, visit_count, last_visit_date in cur.fetchall():
            rows.append({
                "url": url or "",
                "title": title or "",
                "visit_count": visit_count or 0,
                "last_visit_time": _micros_to_dt(last_visit_date),
            })
        return rows
    finally:
        conn.close()


def parse_cookies(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT host, name, path, expiry, isSecure, isHttpOnly, lastAccessed "
            "FROM moz_cookies ORDER BY lastAccessed DESC"
        )
        rows = []
        for host, name, path, expiry, is_secure, is_httponly, last_accessed in cur.fetchall():
            rows.append({
                "host": host or "",
                "name": name or "",
                "path": path or "",
                "expires_utc": _seconds_to_dt(expiry),
                "is_secure": bool(is_secure),
                "is_httponly": bool(is_httponly),
                "last_access_utc": _micros_to_dt(last_accessed),
                "value": "Protected",
            })
        return rows
    finally:
        conn.close()


def parse_logins(json_path) -> list[dict]:
    """Firefox stores logins in logins.json, encrypted with the profile's NSS
    key. We never attempt decryption -- origin only; username/password are
    always surfaced as 'Protected (encrypted)' rather than the ciphertext."""
    path = Path(json_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows = []
    for entry in data.get("logins", []):
        created = entry.get("timeCreated")
        created_dt = None
        if created:
            try:
                created_dt = datetime.utcfromtimestamp(int(created) / 1000)
            except (ValueError, OSError, OverflowError):
                created_dt = None
        rows.append({
            "site": entry.get("hostname", ""),
            "username": "Protected (encrypted)",
            "password_value": "Protected",
            "date_created": created_dt,
        })
    return rows
