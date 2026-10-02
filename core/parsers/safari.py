"""
Parser for Safari's History.db (macOS). Safari stores timestamps as
"Mac absolute time" -- seconds since 2001-01-01 UTC -- which differs from
both the Chromium and Firefox epochs, so it gets its own conversion helper.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from core.utils import open_readonly

_MAC_EPOCH = datetime(2001, 1, 1)


def _mac_time_to_dt(value):
    if value in (None, 0, ""):
        return None
    try:
        return _MAC_EPOCH + timedelta(seconds=float(value))
    except (ValueError, OverflowError, OSError):
        return None


def parse_history(db_path) -> list[dict]:
    conn = open_readonly(db_path)
    try:
        cur = conn.execute(
            "SELECT history_items.url AS url, history_visits.title AS title, "
            "history_items.visit_count AS visit_count, history_visits.visit_time AS visit_time "
            "FROM history_visits JOIN history_items ON history_visits.history_item = history_items.id "
            "ORDER BY history_visits.visit_time DESC"
        )
        rows = []
        for url, title, visit_count, visit_time in cur.fetchall():
            rows.append({
                "url": url or "",
                "title": title or "",
                "visit_count": visit_count or 0,
                "last_visit_time": _mac_time_to_dt(visit_time),
            })
        return rows
    finally:
        conn.close()
