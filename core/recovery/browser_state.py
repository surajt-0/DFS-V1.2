"""Browser *system data* recovery: the non-database state a browser keeps
about what the user was doing -- and, crucially, the parts that survive
after the user "cleared history":

  session      Chromium SNSS files (Current/Last Session, Current/Last Tabs,
               Session_*, Tabs_*): open tabs + their back/forward navigation
               history. Firefox sessionstore (recovery.jsonlz4, previous,
               sessionstore): open tabs, and **recently closed tabs/windows**.
  bookmarks    Chromium Bookmarks / Bookmarks.bak; Firefox bookmarkbackups.
               A .bak/older backup can still hold entries deleted from the
               current file (the service layer diffs them).
  extensions   Installed extensions (Chromium Preferences, Firefox
               extensions.json) with install times.
  preferences  Home page, startup pages, download folder, proxy/DoH settings,
               profile/account labels (Chromium Preferences / Local State,
               Firefox prefs.js).
  network      Chromium "Network Persistent State": hosts the browser
               talked to (server list), including ones absent from History.

Every function takes a path to a working COPY and returns StateItem rows.
Nothing is written, and no credential material is read: cookie values,
saved passwords and sync tokens are not touched by any code here.
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .mozlz4 import read_mozlz4

MAX_ITEMS = 20000
MAX_FILE = 128 * 1024 * 1024

CAT_SESSION, CAT_BOOKMARK, CAT_EXTENSION = "session", "bookmark", "extension"
CAT_PREF, CAT_NETWORK, CAT_COMPANION = "preference", "network", "companion"

_CH = datetime(1601, 1, 1)
_UX = datetime(1970, 1, 1)


@dataclass
class StateItem:
    category: str
    browser: str
    name: str                    # primary text (URL, extension name, setting name, host)
    value: str = ""              # secondary text (title, value, ...)
    timestamp: Optional[datetime] = None
    status: str = "present"      # present | recovered_closed | prior_navigation | backup_only
    source_file: str = ""
    detail: dict = field(default_factory=dict)


class StateError(Exception):
    pass


def _chrome_dt(v):
    try:
        v = int(v)
        if v <= 0:
            return None
        return _CH + timedelta(microseconds=v)
    except (ValueError, OverflowError, TypeError):
        return None


def _unix_us(v):
    try:
        v = int(v)
        return _UX + timedelta(microseconds=v) if v > 0 else None
    except (ValueError, OverflowError, TypeError):
        return None


def _unix_ms(v):
    try:
        v = int(v)
        return _UX + timedelta(milliseconds=v) if v > 0 else None
    except (ValueError, OverflowError, TypeError):
        return None


def _clip(s, n=2000):
    s = "" if s is None else str(s)
    return s[:n]


def _load_json(path):
    p = Path(path)
    if p.stat().st_size > MAX_FILE:
        raise StateError("File is too large to parse safely.")
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="strict"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise StateError(f"Not valid JSON ({exc}).") from exc


# ---------------------------------------------------------------------------
# Classification by (original) file name
# ---------------------------------------------------------------------------
_SNSS_RE = re.compile(r"^(current session|last session|current tabs|last tabs|session_\d+|tabs_\d+)$")


def classify_state_file(name: str):
    """-> (category, browser, subtype) or None. Purely name-based; content
    is validated by the parser (bad content = a clear parse error)."""
    n = (name or "").strip().lower()
    if n.endswith(("-wal", "-journal")):
        return CAT_COMPANION, "sqlite", "companion"
    if _SNSS_RE.match(n):
        return CAT_SESSION, "chromium", "snss"
    if n in ("recovery.jsonlz4", "recovery.baklz4", "previous.jsonlz4", "sessionstore.jsonlz4"):
        return CAT_SESSION, "firefox", "sessionstore"
    if n in ("bookmarks", "bookmarks.bak"):
        return CAT_BOOKMARK, "chromium", "bookmarks.bak" if n.endswith(".bak") else "bookmarks"
    if n.startswith("bookmarks-") and n.endswith(".jsonlz4"):
        return CAT_BOOKMARK, "firefox", "bookmarkbackup"
    if n in ("preferences", "secure preferences", "local state"):
        return CAT_PREF, "chromium", n
    if n == "prefs.js":
        return CAT_PREF, "firefox", "prefs.js"
    if n == "extensions.json":
        return CAT_EXTENSION, "firefox", "extensions.json"
    if n == "network persistent state":
        return CAT_NETWORK, "chromium", "network_state"
    return None


# ---------------------------------------------------------------------------
# Chromium SNSS session files
# ---------------------------------------------------------------------------
_URL_RE = re.compile(rb"(?:https?|file|ftp)://[\x21-\x7e]{3,2000}")


def _pad4(n):
    return (n + 3) & ~3


def _snss_commands(data: bytes):
    if len(data) < 8 or data[:4] != b"SNSS":
        raise StateError("Not a Chromium SNSS session file (missing 'SNSS' header).")
    pos, n = 8, len(data)
    while pos + 3 <= n:
        (size,) = struct.unpack_from("<H", data, pos)
        if size < 1 or pos + 2 + size > n:
            break  # truncated/torn last command: keep what we have
        cid = data[pos + 2]
        yield cid, data[pos + 3: pos + 2 + size]
        pos += 2 + size


def _snss_nav(payload: bytes):
    """kCommandUpdateTabNavigation pickle -> (tab_id, index, url, title)."""
    if len(payload) < 20:
        return None
    (psize,) = struct.unpack_from("<I", payload, 0)
    if psize + 4 > len(payload) + 3 or psize < 16:
        return None
    tab_id, index, ulen = struct.unpack_from("<iiI", payload, 4)
    if not (0 <= ulen <= 4096) or 16 + ulen > len(payload):
        return None
    url = payload[16:16 + ulen].decode("utf-8", "replace")
    pos = 16 + _pad4(ulen)
    title = ""
    if pos + 4 <= len(payload):
        (tlen,) = struct.unpack_from("<I", payload, pos)
        if 0 <= tlen <= 2048 and pos + 4 + tlen * 2 <= len(payload):
            title = payload[pos + 4: pos + 4 + tlen * 2].decode("utf-16-le", "replace")
    if not url.lower().startswith(("http://", "https://", "file://", "ftp://", "chrome://", "about:")):
        return None
    return tab_id, index, url, title


def parse_snss(path, source_file="", browser="chromium") -> list:
    data = Path(path).read_bytes()[:MAX_FILE]
    items, seen = [], set()
    for cid, payload in _snss_commands(data):
        if cid != 6:
            continue
        nav = _snss_nav(payload)
        if not nav:
            continue
        tab_id, index, url, title = nav
        key = (tab_id, index, url)
        if key in seen:
            continue
        seen.add(key)
        items.append(StateItem(CAT_SESSION, browser, _clip(url, 8192), _clip(title, 500), None,
                               "present", source_file, {"tab_id": tab_id, "nav_index": index}))
        if len(items) >= MAX_ITEMS:
            break
    if not items:
        # Damaged/unfamiliar layout: fall back to URL string carving so the
        # examiner still gets leads, clearly marked as low-fidelity.
        for m in _URL_RE.finditer(data):
            u = m.group(0).decode("ascii", "ignore")
            if u not in seen:
                seen.add(u)
                items.append(StateItem(CAT_SESSION, browser, _clip(u, 8192), "", None, "present",
                                       source_file, {"carved_from_raw_bytes": True}))
            if len(items) >= MAX_ITEMS:
                break
    return items


# ---------------------------------------------------------------------------
# Firefox session store
# ---------------------------------------------------------------------------
def _ff_entries(entries, status, src, ctx, ts=None):
    out = []
    for i, e in enumerate(entries or []):
        if not isinstance(e, dict) or not e.get("url"):
            continue
        out.append(StateItem(CAT_SESSION, "firefox", _clip(e["url"], 8192), _clip(e.get("title"), 500), ts,
                             status if i == len(entries) - 1 or status != "present" else "prior_navigation",
                             src, dict(ctx, nav_index=i)))
    return out


def parse_firefox_session(path, source_file="") -> list:
    try:
        raw = read_mozlz4(path)
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise StateError(f"Couldn't decode Firefox session file ({exc}).") from exc
    items = []
    for wi, win in enumerate(doc.get("windows") or []):
        for ti, tab in enumerate((win or {}).get("tabs") or []):
            items += _ff_entries(tab.get("entries"), "present", source_file, {"window": wi, "tab": ti},
                                 _unix_ms(tab.get("lastAccessed")))
        for ct in (win or {}).get("_closedTabs") or []:
            st = (ct or {}).get("state") or {}
            items += _ff_entries(st.get("entries"), "recovered_closed", source_file,
                                 {"window": wi, "closed_tab": True}, _unix_ms((ct or {}).get("closedAt")))
    for cw in doc.get("_closedWindows") or []:
        for ti, tab in enumerate((cw or {}).get("tabs") or []):
            items += _ff_entries(tab.get("entries"), "recovered_closed", source_file,
                                 {"closed_window": True, "tab": ti}, _unix_ms((cw or {}).get("closedAt")))
    return items[:MAX_ITEMS]


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------
def _walk_chromium_bookmarks(node, folder, out, src, sub, browser="chromium"):
    if not isinstance(node, dict):
        return
    t = node.get("type")
    if t == "url" and node.get("url"):
        out.append(StateItem(CAT_BOOKMARK, browser, _clip(node["url"], 8192), _clip(node.get("name"), 500),
                             _chrome_dt(node.get("date_added")), "present", src,
                             {"folder": folder, "guid": node.get("guid", ""), "backup": sub != "bookmarks",
                              "last_used": (_chrome_dt(node.get("date_last_used")) or "") and
                                           _chrome_dt(node.get("date_last_used")).isoformat()}))
    for ch in node.get("children") or []:
        _walk_chromium_bookmarks(ch, f"{folder}/{node.get('name', '')}".strip("/"), out, src, sub, browser)


def parse_bookmarks(path, subtype, source_file="") -> list:
    items = []
    if subtype in ("bookmarks", "bookmarks.bak"):
        doc = _load_json(path)
        for root in (doc.get("roots") or {}).values():
            _walk_chromium_bookmarks(root, "", items, source_file, subtype)
    else:  # Firefox JSON backup (mozlz4)
        try:
            doc = json.loads(read_mozlz4(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StateError(f"Couldn't decode Firefox bookmark backup ({exc}).") from exc

        def walk(n, folder):
            if not isinstance(n, dict):
                return
            if n.get("uri") and n.get("type") == "text/x-moz-place":
                items.append(StateItem(CAT_BOOKMARK, "firefox", _clip(n["uri"], 8192), _clip(n.get("title"), 500),
                                       _unix_us(n.get("dateAdded")), "present", source_file,
                                       {"folder": folder, "backup": True}))
            for ch in n.get("children") or []:
                walk(ch, f"{folder}/{n.get('title', '')}".strip("/"))
        walk(doc, "")
    return items[:MAX_ITEMS]


# ---------------------------------------------------------------------------
# Preferences / extensions / network state
# ---------------------------------------------------------------------------
def _dig(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def parse_chromium_prefs(path, subtype, source_file="") -> list:
    doc = _load_json(path)
    items = []

    def pref(name, val, **detail):
        if val in (None, "", [], {}):
            return
        v = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
        items.append(StateItem(CAT_PREF, "chromium", name, _clip(v, 1000), None, "present", source_file, detail))

    pref("profile.name", _dig(doc, "profile", "name"))
    pref("homepage", doc.get("homepage"))
    pref("session.startup_urls", _dig(doc, "session", "startup_urls"))
    pref("download.default_directory", _dig(doc, "download", "default_directory"))
    pref("savefile.default_directory", _dig(doc, "savefile", "default_directory"))
    pref("dns_over_https.mode", _dig(doc, "dns_over_https", "mode"), dns=True)
    pref("dns_over_https.templates", _dig(doc, "dns_over_https", "templates"), dns=True)
    pref("proxy", doc.get("proxy"), dns=True)
    for acct in doc.get("account_info") or []:
        if isinstance(acct, dict) and acct.get("email"):
            items.append(StateItem(CAT_PREF, "chromium", "signed-in account", _clip(acct["email"], 300), None,
                                   "present", source_file, {"full_name": _clip(acct.get("full_name"), 200)}))
    exts = _dig(doc, "extensions", "settings")
    if isinstance(exts, dict):
        for ext_id, e in exts.items():
            if not isinstance(e, dict):
                continue
            man = e.get("manifest") if isinstance(e.get("manifest"), dict) else {}
            name = man.get("name") or e.get("path") or ext_id
            items.append(StateItem(
                CAT_EXTENSION, "chromium", _clip(name, 300), _clip(man.get("version"), 60),
                _chrome_dt(e.get("first_install_time") or e.get("install_time")), "present", source_file,
                {"id": ext_id, "state": e.get("state"), "from_webstore": e.get("from_webstore"),
                 "location": e.get("location"), "path": _clip(e.get("path"), 500),
                 "permissions": [str(x) for x in (_dig(e, "active_permissions", "api") or [])][:25]}))
    return items[:MAX_ITEMS]


_PREF_RE = re.compile(r'^\s*user_pref\("([^"]+)",\s*(.*?)\);\s*$')
_FF_PREFS = ("browser.startup.homepage", "network.proxy.", "network.trr.", "browser.download.dir",
             "browser.download.lastDir", "network.dns.", "network.trr.mode", "browser.privatebrowsing",
             "places.history.enabled", "privacy.clearOnShutdown", "privacy.sanitize", "extensions.lastAppVersion",
             "app.update.lastUpdateTime", "browser.startup.page")


def parse_firefox_prefs(path, source_file="") -> list:
    items = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _PREF_RE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"')
        if any(key.startswith(p) for p in _FF_PREFS):
            items.append(StateItem(CAT_PREF, "firefox", key, _clip(val, 1000), None, "present", source_file,
                                   {"dns": key.startswith(("network.trr.", "network.dns.", "network.proxy."))}))
    return items[:MAX_ITEMS]


def parse_firefox_extensions(path, source_file="") -> list:
    doc = _load_json(path)
    items = []
    for a in doc.get("addons") or []:
        if not isinstance(a, dict):
            continue
        name = _dig(a, "defaultLocale", "name") or a.get("id")
        items.append(StateItem(CAT_EXTENSION, "firefox", _clip(name, 300), _clip(a.get("version"), 60),
                               _unix_ms(a.get("installDate")), "present", source_file,
                               {"id": a.get("id"), "active": a.get("active"), "type": a.get("type"),
                                "location": a.get("location")}))
    return items[:MAX_ITEMS]


def parse_network_state(path, source_file="") -> list:
    doc = _load_json(path)
    items = []
    servers = _dig(doc, "net", "http_server_properties", "servers") or []
    for s in servers:
        if not isinstance(s, dict) or not s.get("server"):
            continue
        items.append(StateItem(CAT_NETWORK, "chromium", _clip(s["server"], 500),
                               "alt-svc" if s.get("alternative_service") else "", None, "present",
                               source_file, {"supports_spdy": s.get("supports_spdy"),
                                             "network_anonymization_key": _clip(s.get("anonymization"), 200)}))
    return items[:MAX_ITEMS]


# ---------------------------------------------------------------------------
def parse_state_file(path, original_name: str) -> list:
    """Dispatch on the ORIGINAL file name. Raises StateError for content
    that doesn't match what its name promises."""
    cls = classify_state_file(original_name)
    if not cls:
        raise StateError("Unrecognised browser state file name.")
    cat, browser, sub = cls
    src = original_name
    try:
        if cat == CAT_COMPANION:
            return []
        if cat == CAT_SESSION and sub == "snss":
            return parse_snss(path, src)
        if cat == CAT_SESSION:
            return parse_firefox_session(path, src)
        if cat == CAT_BOOKMARK:
            return parse_bookmarks(path, sub, src)
        if cat == CAT_PREF and browser == "chromium":
            return parse_chromium_prefs(path, sub, src)
        if cat == CAT_PREF:
            return parse_firefox_prefs(path, src)
        if cat == CAT_EXTENSION:
            return parse_firefox_extensions(path, src)
        if cat == CAT_NETWORK:
            return parse_network_state(path, src)
    except StateError:
        raise
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        raise StateError(f"Couldn't parse {original_name}: {exc}") from exc
    return []
