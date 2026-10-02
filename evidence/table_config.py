"""Single source of truth for the 5 normalized artifact tables (history,
login, cookie, download, cache): which model backs them, which evidence
types feed them, search/sort/export field lists. Used by both the
server-rendered generic table view (evidence/views.py) and the JSON API
(evidence/api.py) so the two never drift apart.
"""
from .models import (
    CacheEntry, CookieEntry, DownloadEntry, EvidenceItem, HistoryEntry, LoginEntry,
)

TABLE_CONFIG = {
    "history": {
        "model": HistoryEntry, "related": "history_entries",
        "search_fields": ["url", "title"],
        "columns": [
            ("last_visit_time", "Last Visit"), ("title", "Title"), ("url", "URL"), ("visit_count", "Visits"),
        ],
        "default_sort": "-last_visit_time",
        "template": "evidence/table_generic.html", "row_kind": "history",
        "kinds": [EvidenceItem.EvidenceType.CHROMIUM_HISTORY, EvidenceItem.EvidenceType.FIREFOX_HISTORY,
                  EvidenceItem.EvidenceType.SAFARI_HISTORY],
        "export_fields": ["last_visit_time", "title", "url", "visit_count"],
        "export_headers": ["Last Visit", "Title", "URL", "Visit Count"],
    },
    "login": {
        "model": LoginEntry, "related": "login_entries",
        "search_fields": ["site", "username"],
        "columns": [
            ("date_created", "Created"), ("site", "Site"), ("username", "Username"), ("password_value", "Password"),
        ],
        "default_sort": "-date_created",
        "template": "evidence/table_generic.html", "row_kind": "login",
        "kinds": [EvidenceItem.EvidenceType.CHROMIUM_LOGINS, EvidenceItem.EvidenceType.FIREFOX_LOGINS],
        "export_fields": ["date_created", "site", "username", "password_value"],
        "export_headers": ["Created", "Site", "Username", "Password"],
    },
    "cookie": {
        "model": CookieEntry, "related": "cookie_entries",
        "search_fields": ["host", "name", "path"],
        "columns": [
            ("last_access_utc", "Last Access"), ("host", "Host"), ("name", "Name"),
            ("path", "Path"), ("expires_utc", "Expires"), ("is_secure", "Secure"), ("is_httponly", "HttpOnly"),
        ],
        "default_sort": "-last_access_utc",
        "template": "evidence/table_generic.html", "row_kind": "cookie",
        "kinds": [EvidenceItem.EvidenceType.CHROMIUM_COOKIES, EvidenceItem.EvidenceType.FIREFOX_COOKIES],
        "export_fields": ["last_access_utc", "host", "name", "path", "expires_utc", "is_secure", "is_httponly", "value"],
        "export_headers": ["Last Access", "Host", "Name", "Path", "Expires", "Secure", "HttpOnly", "Value"],
    },
    "download": {
        "model": DownloadEntry, "related": "download_entries",
        "search_fields": ["target_path", "source_url", "referrer", "state", "danger_type"],
        "columns": [
            ("start_time", "Started"), ("target_path", "Saved As"), ("source_url", "Source URL"),
            ("total_bytes", "Size"), ("state", "State"), ("danger_type", "Danger"),
        ],
        "default_sort": "-start_time",
        "template": "evidence/table_generic.html", "row_kind": "download",
        "kinds": [EvidenceItem.EvidenceType.CHROMIUM_DOWNLOADS],
        "export_fields": ["start_time", "target_path", "source_url", "referrer", "total_bytes", "state", "danger_type"],
        "export_headers": ["Started", "Saved As", "Source URL", "Referrer", "Bytes", "State", "Danger"],
    },
    "cache": {
        "model": CacheEntry, "related": "cache_entries",
        "search_fields": ["name", "path", "mime_guess"],
        "columns": [
            ("modified", "Modified"), ("name", "Name"), ("path", "Path"),
            ("mime_guess", "MIME"), ("size_bytes", "Size"),
        ],
        "default_sort": "-modified",
        "template": "evidence/table_generic.html", "row_kind": "cache",
        "kinds": [EvidenceItem.EvidenceType.CACHE_ARCHIVE],
        "export_fields": ["modified", "name", "path", "mime_guess", "size_bytes"],
        "export_headers": ["Modified", "Name", "Path", "MIME", "Size"],
    },
}

SORT_WHITELIST = {c[0] for cfg in TABLE_CONFIG.values() for c in cfg["columns"]}

EXPORT_FEATURE_MAP = {
    "csv": "feature_csv_export",
    "xlsx": "feature_xlsx_export",
    "json": "feature_json_export",
}
