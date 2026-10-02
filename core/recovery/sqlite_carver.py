"""
Recovers deleted browser records from SQLite databases (Chromium
History / Cookies / Login Data, Firefox places.sqlite / cookies.sqlite).

Why deleted rows are often still recoverable
--------------------------------------------
SQLite does not scrub data when a row is deleted (unless PRAGMA
secure_delete is on). Depending on how the delete happened the old bytes
end up in one of four places, each of which this module inspects:

  freelist_page  A whole b-tree page emptied by the delete is returned to
                 the freelist with its old contents intact. Its cell
                 pointer array is usually still valid, so complete cells
                 (payload length + rowid + record) can be read back.
  freeblock      A single deleted cell inside a page that still has live
                 rows becomes a "freeblock" (first 4 bytes overwritten by
                 the freeblock header) or is left in the unallocated gap
                 between the cell-pointer array and the cell-content area.
  wal            Older/newer page images inside the -wal file that have
                 not been checkpointed into the main database yet.
  wal_stale      Frames left behind in the -wal file from an earlier WAL
                 generation (salts no longer match the WAL header).

Everything found is validated against the live table schema and strict
plausibility checks (URL scheme, timestamp range, ...) so random bytes
don't turn into fake evidence, and every result carries a confidence:

  high    complete cell whose stored payload length equals the size
          computed from its own record header (integrity-checked)
  medium  record header intact, OR only its length byte was overwritten
          (SQLite's freeblock header) and was rebuilt from the table
          schema; body decoded and passed strict plausibility checks
  low     two header bytes lost (length byte + the NULL rowid-alias
          column) and rebuilt on an assumption about the schema --
          treat as a lead to verify, not as proof

Limitations (also surfaced to the examiner): nothing is recoverable if
secure_delete was on, after VACUUM, or once pages were overwritten by
later inserts; records whose payload spilled to overflow pages are
skipped; Safari's split history schema and UTF-16 databases are not
supported; WAL frame checksums are not verified.

Privacy: only the columns listed in KNOWN_TABLES[...]["wanted"] are ever
decoded. password_value / value / encrypted_value are not in any list.
"""
from __future__ import annotations

import re
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

SQLITE_MAGIC = b"SQLite format 3\x00"
WAL_MAGICS = (0x377F0682, 0x377F0683)

CONF_HIGH, CONF_MEDIUM, CONF_LOW = "high", "medium", "low"
_CONF_RANK = {CONF_HIGH: 3, CONF_MEDIUM: 2, CONF_LOW: 1}

SRC_FREELIST = "freelist_page"
SRC_FREEBLOCK = "freeblock"
SRC_WAL = "wal"
SRC_WAL_STALE = "wal_stale"

ST_DELETED = "deleted"
ST_OLDER = "older_version"
ST_WAL_ONLY = "wal_only"


class CarveError(Exception):
    """The file can't be carved at all (not SQLite, unreadable, ...)."""


# ---------------------------------------------------------------------------
# Timestamps -- naive UTC datetimes, exactly like core.parsers.*
# ---------------------------------------------------------------------------
_CHROME_EPOCH = datetime(1601, 1, 1)
_UNIX_EPOCH = datetime(1970, 1, 1)


def _us_since(epoch, value):
    try:
        return epoch + timedelta(microseconds=int(value))
    except (ValueError, OverflowError, OSError):
        return None


def _chrome_dt(value):
    return _us_since(_CHROME_EPOCH, value) if value else None


def _unix_us_dt(value):
    return _us_since(_UNIX_EPOCH, value) if value else None


def _unix_s_or_ms_dt(value):
    if not value:
        return None
    try:
        v = int(value)
        if v > 10 ** 11:  # newer Firefox stores cookie expiry in ms
            v //= 1000
        return _UNIX_EPOCH + timedelta(seconds=v)
    except (ValueError, OverflowError, OSError):
        return None


def _range_us(epoch, start_year, end_dt):
    return (
        int((datetime(start_year, 1, 1) - epoch).total_seconds() * 1_000_000),
        int((end_dt - epoch).total_seconds() * 1_000_000),
    )


def _ranges():
    now = datetime.utcnow()
    soon = now + timedelta(days=2 * 365)
    far = datetime(2200, 1, 1)
    return {
        "chrome": _range_us(_CHROME_EPOCH, 1995, soon),
        "chrome_expiry": _range_us(_CHROME_EPOCH, 1995, far),
        "unix": _range_us(_UNIX_EPOCH, 1995, soon),
    }


def _in(v, rng, allow_zero=True):
    if v is None:
        return allow_zero
    if not isinstance(v, int):
        return False
    if v == 0:
        return allow_zero
    return rng[0] <= v <= rng[1]


# ---------------------------------------------------------------------------
# Table specs: what we are willing to extract, and how to sanity-check it
# ---------------------------------------------------------------------------
# NOTE: value / encrypted_value / password_value are deliberately absent.
KNOWN_TABLES = {
    "urls": dict(kind="history", browser="chromium",
                 wanted=("url", "title", "visit_count", "last_visit_time"),
                 required=("url", "last_visit_time")),
    "downloads": dict(kind="download", browser="chromium",
                      wanted=("target_path", "tab_url", "referrer", "total_bytes",
                              "state", "danger_type", "start_time"),
                      required=("target_path", "start_time")),
    "cookies": dict(kind="cookie", browser="chromium",
                    wanted=("host_key", "name", "path", "expires_utc", "is_secure",
                            "is_httponly", "last_access_utc"),
                    required=("host_key", "name")),
    "logins": dict(kind="login", browser="chromium",
                   wanted=("origin_url", "username_value", "date_created"),
                   required=("origin_url",)),
    "moz_places": dict(kind="history", browser="firefox",
                       wanted=("url", "title", "visit_count", "last_visit_date"),
                       required=("url", "last_visit_date")),
    "moz_cookies": dict(kind="cookie", browser="firefox",
                        wanted=("host", "name", "path", "expiry", "lastAccessed",
                                "isSecure", "isHttpOnly"),
                        required=("host", "name")),
}


@dataclass
class TableSpec:
    table: str
    kind: str
    browser: str
    columns: list
    wanted: dict          # field name -> column index
    ncols: int
    min_cols: int
    rowid_alias_first: bool
    col_class: list = field(default_factory=list)   # per column: null/int/real/text/any

    @property
    def hdr_cap(self):
        return min(self.ncols * 9 + 2, 400)


_SCHEMES = ("http://", "https://", "file://", "ftp://", "chrome://", "edge://",
            "about:", "view-source:", "chrome-extension://", "moz-extension://",
            "brave://", "opera://")
_HOST_RE = re.compile(r"^\.?[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)*$")


_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_NONZERO = re.compile(rb"[^\x00]")


def _printable(s, maxlen):
    return isinstance(s, str) and len(s) <= maxlen and not _CTRL_RE.search(s)


def _is_url(s):
    return isinstance(s, str) and len(s) <= 8192 and s.lower().startswith(_SCHEMES) and _printable(s, 8192)


def _validate(spec: TableSpec, v: dict, rng, strict: bool) -> bool:
    """Plausibility gate. `strict` (record header was reconstructed, i.e.
    low confidence) additionally requires the main timestamp to be present
    and in range."""
    t, k = spec.table, spec.kind
    if t == "urls":
        if not (_is_url(v.get("url")) and (v.get("title") is None or _printable(v["title"], 2000))):
            return False
        if not (isinstance(v.get("visit_count"), int) and 0 <= v["visit_count"] < 10_000_000):
            return False
        return _in(v.get("last_visit_time"), rng["chrome"], allow_zero=not strict)
    if t == "moz_places":
        if not (_is_url(v.get("url")) and (v.get("title") is None or _printable(v["title"], 2000))):
            return False
        vc = v.get("visit_count")
        if vc is not None and not (isinstance(vc, int) and 0 <= vc < 10_000_000):
            return False
        return _in(v.get("last_visit_date"), rng["unix"], allow_zero=not strict)
    if t == "downloads":
        p = v.get("target_path")
        if not (isinstance(p, str) and 2 < len(p) <= 4096 and ("/" in p or "\\" in p) and _printable(p, 4096)):
            return False
        for f in ("tab_url", "referrer"):
            if v.get(f) is not None and not (isinstance(v[f], str) and len(v[f]) <= 8192 and _printable(v[f], 8192)):
                return False
        st = v.get("state")
        if st is not None and not (isinstance(st, int) and 0 <= st <= 10):
            return False
        tb = v.get("total_bytes")
        if tb is not None and not (isinstance(tb, int) and -1 <= tb < 2 ** 50):
            return False
        return _in(v.get("start_time"), rng["chrome"], allow_zero=not strict)
    if t == "cookies":
        h, n, p = v.get("host_key"), v.get("name"), v.get("path")
        if not (isinstance(h, str) and 1 < len(h) <= 255 and _HOST_RE.match(h)):
            return False
        if not (isinstance(n, str) and 0 < len(n) <= 4096 and _printable(n, 4096)):
            return False
        if p is not None and not (isinstance(p, str) and p.startswith("/") and len(p) <= 2048 and _printable(p, 2048)):
            return False
        for f in ("is_secure", "is_httponly"):
            if v.get(f) is not None and v[f] not in (0, 1):
                return False
        return (_in(v.get("expires_utc"), rng["chrome_expiry"])
                and _in(v.get("last_access_utc"), rng["chrome"], allow_zero=not strict))
    if t == "moz_cookies":
        h, n, p = v.get("host"), v.get("name"), v.get("path")
        if not (isinstance(h, str) and 1 < len(h) <= 255 and _HOST_RE.match(h)):
            return False
        if not (isinstance(n, str) and 0 < len(n) <= 4096 and _printable(n, 4096)):
            return False
        if p is not None and not (isinstance(p, str) and p.startswith("/") and len(p) <= 2048):
            return False
        for f in ("isSecure", "isHttpOnly"):
            if v.get(f) is not None and v[f] not in (0, 1):
                return False
        return _in(v.get("lastAccessed"), rng["unix"], allow_zero=not strict)
    if t == "logins":
        o, u = v.get("origin_url"), v.get("username_value")
        if not (isinstance(o, str) and o.lower().startswith(("http://", "https://")) and _printable(o, 8192)):
            return False
        if u is not None and not _printable(u, 500):
            return False
        return _in(v.get("date_created"), rng["chrome"], allow_zero=not strict)
    return False


def _normalize(spec: TableSpec, v: dict) -> dict:
    """-> primary, secondary, event_time (naive UTC), detail, ident, exact.
    `ident` identifies the logical record; `exact` also pins its timestamp
    (used to tell 'identical to a live row' from 'older version of one')."""
    t = spec.table
    if t == "urls":
        et = _chrome_dt(v.get("last_visit_time"))
        return dict(primary=v["url"], secondary=v.get("title") or "", event_time=et,
                    detail={"visit_count": v.get("visit_count") or 0},
                    ident=(v["url"],), exact=(v["url"], et))
    if t == "moz_places":
        et = _unix_us_dt(v.get("last_visit_date"))
        return dict(primary=v["url"], secondary=v.get("title") or "", event_time=et,
                    detail={"visit_count": v.get("visit_count") or 0},
                    ident=(v["url"],), exact=(v["url"], et))
    if t == "downloads":
        et = _chrome_dt(v.get("start_time"))
        return dict(primary=v["target_path"], secondary=v.get("tab_url") or "", event_time=et,
                    detail={"referrer": v.get("referrer") or "", "total_bytes": v.get("total_bytes") or 0,
                            "state": v.get("state"), "danger_type": v.get("danger_type")},
                    ident=(v["target_path"],), exact=(v["target_path"], et))
    if t == "cookies":
        et = _chrome_dt(v.get("last_access_utc"))
        ident = (v["host_key"], v["name"], v.get("path") or "")
        exp = _chrome_dt(v.get("expires_utc"))
        return dict(primary=v["host_key"], secondary=v["name"], event_time=et,
                    detail={"path": v.get("path") or "", "expires": exp.isoformat() if exp else None,
                            "secure": bool(v.get("is_secure")), "httponly": bool(v.get("is_httponly")),
                            "value": "Protected"},
                    ident=ident, exact=ident + (et,))
    if t == "moz_cookies":
        et = _unix_us_dt(v.get("lastAccessed"))
        ident = (v["host"], v["name"], v.get("path") or "")
        exp = _unix_s_or_ms_dt(v.get("expiry"))
        return dict(primary=v["host"], secondary=v["name"], event_time=et,
                    detail={"path": v.get("path") or "", "expires": exp.isoformat() if exp else None,
                            "secure": bool(v.get("isSecure")), "httponly": bool(v.get("isHttpOnly")),
                            "value": "Protected"},
                    ident=ident, exact=ident + (et,))
    if t == "logins":
        et = _chrome_dt(v.get("date_created"))
        ident = (v["origin_url"], v.get("username_value") or "")
        return dict(primary=v["origin_url"], secondary=v.get("username_value") or "", event_time=et,
                    detail={"password": "Protected"}, ident=ident, exact=ident + (et,))
    raise ValueError(t)


# ---------------------------------------------------------------------------
# Low-level record decoding
# ---------------------------------------------------------------------------
_FIXED = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8, 7: 8, 8: 0, 9: 0}


def _varint(buf, pos, limit):
    v = 0
    for i in range(8):
        p = pos + i
        if p >= limit:
            return None
        b = buf[p]
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, i + 1
    p = pos + 8
    if p >= limit:
        return None
    return (v << 8) | buf[p], 9


def _serial_size(t):
    if t <= 9:
        return _FIXED[t]
    if t < 12:
        return -1
    return (t - 12) // 2 if t % 2 == 0 else (t - 13) // 2


def _type_ok(cls, t):
    """Can a column of declared affinity `cls` hold serial type `t`?  This is
    the early-reject that keeps byte-scanning fast: random bytes almost never
    satisfy the schema's column types for more than one or two columns."""
    if t == 10 or t == 11:
        return False
    if cls == "any":
        return True
    if cls == "int":
        return t <= 6 or t == 8 or t == 9
    if cls == "text":
        return t == 0 or (t >= 13 and t & 1 == 1)
    if cls == "null":
        return t == 0
    return t <= 9   # real


def _affinity_class(decl, rowid_alias):
    if rowid_alias:
        return "null"          # INTEGER PRIMARY KEY is stored as NULL in the record
    d = (decl or "").upper()
    if "INT" in d:
        return "int"
    if "CHAR" in d or "CLOB" in d or "TEXT" in d:
        return "text"
    if "REAL" in d or "FLOA" in d or "DOUB" in d:
        return "real"
    return "any"


def _decode(t, data):
    if t == 0:
        return None
    if 1 <= t <= 6:
        return int.from_bytes(data, "big", signed=True)
    if t == 7:
        return struct.unpack(">d", data)[0]
    if t == 8:
        return 0
    if t == 9:
        return 1
    if t % 2 == 0:
        return bytes(data)
    return bytes(data).decode("utf-8")


def _decode_wanted(buf, body_start, limit, serials, spec):
    """Walk the serial types once, decoding only whitelisted columns."""
    want = {idx: name for name, idx in spec.wanted.items()}
    pos = body_start
    out = {}
    try:
        for idx, t in enumerate(serials):
            sz = _serial_size(t)
            if sz < 0 or pos + sz > limit:
                return None
            if idx in want:
                out[want[idx]] = _decode(t, buf[pos:pos + sz])
            pos += sz
    except (UnicodeDecodeError, struct.error, ValueError):
        return None
    for name in spec.wanted:
        out.setdefault(name, None)
    return out, pos - body_start


def _parse_record(buf, start, limit, spec: TableSpec):
    """Record with an intact header. -> (values, hdr_len, body_len) | None"""
    r = _varint(buf, start, limit)
    if r is None:
        return None
    hdr_len, n = r
    if hdr_len < 2 or hdr_len > spec.hdr_cap or start + hdr_len > limit:
        return None
    pos, hdr_end, serials = start + n, start + hdr_len, []
    cls = spec.col_class
    while pos < hdr_end:
        r = _varint(buf, pos, hdr_end)
        if r is None:
            return None
        t, m = r
        j = len(serials)
        if j >= spec.ncols or not _type_ok(cls[j], t):
            return None
        serials.append(t)
        pos += m
    if pos != hdr_end or len(serials) < spec.min_cols:
        return None
    dec = _decode_wanted(buf, hdr_end, limit, serials, spec)
    if dec is None:
        return None
    vals, body_len = dec
    return vals, hdr_len, body_len


def _parse_record_reconstructed(buf, start, limit, spec: TableSpec, implied_null_first: bool):
    """Header-length byte (and, for INTEGER PRIMARY KEY tables, the first
    serial type) was overwritten by the freeblock header. Rebuild them from
    the schema: read exactly the remaining serial types and derive the
    header length. -> (values, body_start_consumed) | None"""
    cls = spec.col_class
    ncols = spec.ncols
    j = 1 if implied_null_first else 0
    serials = [0] if implied_null_first else []
    pos = start
    while j < ncols:
        if pos >= limit:
            return None
        t = buf[pos]
        if t < 0x80:
            pos += 1
        else:
            r = _varint(buf, pos, limit)
            if r is None:
                return None
            t, m = r
            pos += m
        if not _type_ok(cls[j], t):
            return None
        serials.append(t)
        j += 1
    dec = _decode_wanted(buf, pos, limit, serials, spec)
    if dec is None:
        return None
    vals, body_len = dec
    return vals, (pos - start) + body_len


def _parse_cell(buf, start, limit, spec: TableSpec, max_local):
    """Full table-leaf cell: payload length, rowid, record. The stored
    payload length must equal the size derived from the record header --
    an integrity check that makes false positives very unlikely.
    -> (values, rowid, cell_len) | None"""
    r1 = _varint(buf, start, limit)
    if r1 is None:
        return None
    payload, n1 = r1
    if payload < 2 or payload > max_local:
        return None
    r2 = _varint(buf, start + n1, limit)
    if r2 is None:
        return None
    rowid, n2 = r2
    if rowid >= 1 << 63:
        rowid -= 1 << 64
    rec_start = start + n1 + n2
    rec = _parse_record(buf, rec_start, min(limit, rec_start + payload), spec)
    if rec is None:
        return None
    vals, hdr_len, body_len = rec
    if hdr_len + body_len != payload:
        return None
    return vals, rowid, n1 + n2 + payload


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class CarvedRecord:
    kind: str
    table: str
    browser: str
    source: str
    confidence: str
    page_no: Optional[int]
    offset: Optional[int]
    rowid: Optional[int]
    primary: str
    secondary: str
    event_time: Optional[datetime]
    detail: dict
    status: str = ST_DELETED
    ident: tuple = ()
    exact: tuple = ()
    live_cell: bool = False  # came from a page's cell-pointer array (a row live in that page image)
    origin: str = ""       # wal: "final" (latest committed image) | "older"
    pinned: bool = False   # True = deleted-in-WAL: still live in the main file by construction


@dataclass
class CarveResult:
    records: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Database / page helpers
# ---------------------------------------------------------------------------
def _read_header(fh):
    fh.seek(0)
    hdr = fh.read(100)
    if len(hdr) < 100 or not hdr.startswith(SQLITE_MAGIC):
        raise CarveError("Not a SQLite database (bad header).")
    page_size = struct.unpack(">H", hdr[16:18])[0]
    if page_size == 1:
        page_size = 65536
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        raise CarveError(f"Invalid SQLite page size ({page_size}).")
    return dict(
        page_size=page_size,
        reserved=hdr[20],
        freelist_trunk=struct.unpack(">I", hdr[32:36])[0],
        freelist_count=struct.unpack(">I", hdr[36:40])[0],
        encoding=struct.unpack(">I", hdr[56:60])[0],
        secure_delete_hint=False,
    )


def _walk_freelist_pages(read_page, trunk, npages, usable):
    """-> (trunk_pages:set, leaf_pages:set). `read_page(pgno) -> bytes`.
    Loop/range-guarded: a damaged freelist must never hang or crash a run."""
    trunks, leaves = set(), set()
    while trunk and trunk not in trunks and 1 <= trunk <= npages:
        trunks.add(trunk)
        page = read_page(trunk)
        if len(page) < 8:
            break
        nxt, count = struct.unpack(">II", page[:8])
        for i in range(min(count, usable // 4 - 2)):
            (leaf,) = struct.unpack(">I", page[8 + 4 * i: 12 + 4 * i])
            if 1 <= leaf <= npages:
                leaves.add(leaf)
        trunk = nxt
    return trunks, leaves


def _walk_freelist(fh, hdr, npages):
    ps = hdr["page_size"]

    def read_page(pg):
        fh.seek((pg - 1) * ps)
        return fh.read(ps)

    return _walk_freelist_pages(read_page, hdr["freelist_trunk"], npages, ps - hdr["reserved"])


def build_specs(conn) -> list:
    specs = []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name, meta in KNOWN_TABLES.items():
        if name not in tables:
            continue
        info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        cols = [r[1] for r in info]
        if not all(c in cols for c in meta["required"]):
            continue
        wanted = {c: cols.index(c) for c in meta["wanted"] if c in cols}
        first = info[0] if info else None
        rowid_alias = bool(first and first[5] == 1 and (first[2] or "").upper() == "INTEGER"
                           and sum(1 for r in info if r[5]) == 1)
        min_cols = max(cols.index(c) for c in meta["required"]) + 1
        classes = [_affinity_class(r[2], rowid_alias and i == 0) for i, r in enumerate(info)]
        specs.append(TableSpec(name, meta["kind"], meta["browser"], cols, wanted,
                               len(cols), min_cols, rowid_alias, classes))
    return specs


def _load_live(conn, specs):
    """Keys of rows present in the live (main-file) tables."""
    live = {}
    for spec in specs:
        cols = ", ".join(f'"{c}"' for c in spec.wanted)
        exact, ident = set(), set()
        try:
            for row in conn.execute(f'SELECT {cols} FROM "{spec.table}"'):
                vals = dict(zip(spec.wanted, row))
                try:
                    norm = _normalize(spec, {k: (None if isinstance(v, (bytes, memoryview)) else v)
                                             for k, v in vals.items()})
                except (KeyError, TypeError):
                    continue
                exact.add(norm["exact"])
                ident.add(norm["ident"])
        except sqlite3.Error:
            pass
        live[spec.table] = (exact, ident)
    return live


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
class _Ctx:
    def __init__(self, specs, rng, usable, deadline, max_scan):
        self.specs, self.rng, self.usable = specs, rng, usable
        self.max_local = usable - 35
        self.deadline, self.max_scan = deadline, max_scan
        self.scanned = 0
        self.truncated = False
        self.found = []          # CarvedRecord
        self.candidates = 0
        self.origin = ""

    def budget_ok(self):
        if self.truncated:
            return False
        if self.scanned > self.max_scan or time.monotonic() > self.deadline:
            self.truncated = True
            return False
        return True

    def emit(self, spec, vals, conf, source, page_no, offset, rowid, strict=False, cell=False):
        if not _validate(spec, vals, self.rng, strict):
            return False
        try:
            norm = _normalize(spec, vals)
        except (KeyError, TypeError):
            return False
        self.candidates += 1
        self.found.append(CarvedRecord(
            kind=spec.kind, table=spec.table, browser=spec.browser, source=source,
            confidence=conf, page_no=page_no, offset=offset, rowid=rowid,
            primary=norm["primary"], secondary=norm["secondary"], event_time=norm["event_time"],
            detail=norm["detail"], ident=norm["ident"], exact=norm["exact"], origin=self.origin,
            live_cell=cell,
        ))
        return True


def _scan_region(buf, lo, hi, ctx: _Ctx, source, page_no):
    """Byte-scan [lo, hi) of `buf` for record remnants. At each offset try,
    in order of confidence: full cell -> record with intact header ->
    header-length byte rebuilt from the schema -> header-length byte AND
    NULL first column rebuilt."""
    if hi - lo < 8 or not ctx.budget_ok():
        return
    ctx.scanned += hi - lo
    specs = ctx.specs
    i, end = lo, hi
    while i < end - 4:
        b0 = buf[i]
        if b0 == 0 and buf[i + 1] == 0 and buf[i + 2] == 0:
            # Zero run (typical of scrubbed space). A record can only start
            # at the LAST zero of a run (NULL rowid-alias column + type byte).
            m = _NONZERO.search(buf, i + 3, end)
            i = max(i + 1, (m.start() if m else end) - 1)
            continue
        step = 0
        for spec in specs:
            cell = _parse_cell(buf, i, end, spec, ctx.max_local)
            if cell:
                vals, rowid, ln = cell
                if ctx.emit(spec, vals, CONF_HIGH, source, page_no, i, rowid):
                    step = ln
                    break
            if 2 <= b0 <= spec.hdr_cap and i + b0 <= end and buf[i + b0 - 1] < 0x80:
                rec = _parse_record(buf, i, end, spec)
                if rec:
                    vals, hl, bl = rec
                    if ctx.emit(spec, vals, CONF_MEDIUM, source, page_no, i, None):
                        step = hl + bl
                        break
            for implied in ((False, True) if spec.rowid_alias_first else (False,)):
                rec = _parse_record_reconstructed(buf, i, end, spec, implied)
                if rec:
                    vals, ln = rec
                    conf = CONF_LOW if implied else CONF_MEDIUM
                    if ctx.emit(spec, vals, conf, source, page_no, i, None, strict=True):
                        step = ln
                        break
            if step:
                break
        i += step if step > 0 else 1


def _free_regions(page, hdr_off, ncells, content_start, first_free, usable):
    """Unallocated gap + freeblock chain of a table-leaf page."""
    regions = []
    ptr_end = hdr_off + 8 + 2 * ncells
    if ptr_end < content_start <= usable:
        regions.append((ptr_end, content_start))
    seen, off = set(), first_free
    while off and off not in seen and 4 <= off <= usable - 4:
        seen.add(off)
        nxt, size = struct.unpack(">HH", page[off:off + 4])
        if size < 4 or off + size > usable:
            break
        regions.append((off, off + size))
        off = nxt
    return regions


def _page_layout(page, hdr_off, usable):
    """Parse a table-leaf b-tree page header -> dict | None if not sane."""
    if page[hdr_off] != 0x0D:
        return None
    first_free, ncells, content = struct.unpack(">HHH", page[hdr_off + 1: hdr_off + 7])
    content = content or 65536
    ptr_end = hdr_off + 8 + 2 * ncells
    if ptr_end > usable or content > usable or content < ptr_end - 2 or first_free >= usable:
        return None
    return dict(first_free=first_free, ncells=ncells, content=content, ptr_end=ptr_end)


def _page_cells(page, pgno, ctx: _Ctx, layout):
    """Complete, integrity-checked cells reachable through the pointer array."""
    hdr_off = 100 if pgno == 1 else 0
    base = hdr_off + 8
    for k in range(layout["ncells"]):
        (ptr,) = struct.unpack(">H", page[base + 2 * k: base + 2 * k + 2])
        if not (layout["content"] <= ptr < ctx.usable):
            continue
        for spec in ctx.specs:
            cell = _parse_cell(page, ptr, ctx.usable, spec, ctx.max_local)
            if cell:
                yield spec, cell[0], cell[1], ptr
                break


def _process_page(page, pgno, ctx: _Ctx, source, *, parse_cells: bool, whole_page_scan_if_odd: bool):
    usable = ctx.usable
    hdr_off = 100 if pgno == 1 else 0
    if len(page) < usable:
        return
    layout = _page_layout(page, hdr_off, usable)
    if layout is None:
        if whole_page_scan_if_odd:
            _scan_region(page, hdr_off, usable, ctx, source, pgno)
        return
    if parse_cells:
        for spec, vals, rowid, ptr in _page_cells(page, pgno, ctx, layout):
            ctx.emit(spec, vals, CONF_HIGH, source, pgno, ptr, rowid, cell=True)
    if not ctx.budget_ok():
        return
    for lo, hi in _free_regions(page, hdr_off, layout["ncells"], layout["content"],
                                layout["first_free"], usable):
        _scan_region(page, lo, hi, ctx, source, pgno)


def _index_wal(wal_path, warnings):
    """Read only the 24-byte frame headers. -> (page_size, frames) where each
    frame is (file_offset_of_page, pgno, salts_match, db_size_if_commit_else_0)."""
    frames = []
    with open(wal_path, "rb") as fh:
        head = fh.read(32)
        if len(head) < 32:
            return 0, frames
        magic, _ver, ps, _ck, s1, s2 = struct.unpack(">IIIIII", head[:24])
        if magic not in WAL_MAGICS:
            warnings.append("The -wal file has an unrecognised header and was skipped.")
            return 0, frames
        if ps < 512 or ps > 65536 or ps & (ps - 1):
            warnings.append("The -wal file reports an invalid page size and was skipped.")
            return 0, frames
        pos = 32
        while True:
            fh.seek(pos)
            fhdr = fh.read(24)
            if len(fhdr) < 24:
                break
            if pos + 24 + ps > fh.seek(0, 2):
                break
            pgno, commit, f1, f2 = struct.unpack(">IIII", fhdr[:16])
            if pgno:
                frames.append((pos + 24, pgno, f1 == s1 and f2 == s2, commit))
            pos += 24 + ps
    return ps, frames


def _read_at(path, offset, size):
    with open(path, "rb") as fh:
        fh.seek(offset)
        return fh.read(size)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def carve_database(db_path, wal_path=None, *, max_scan_bytes=64 * 1024 * 1024,
                   max_seconds=180.0) -> CarveResult:
    """Carve deleted/old records out of `db_path` (a safe working COPY) and,
    if given, its `-wal` companion."""
    db_path = Path(db_path)
    res = CarveResult()
    stats = dict(pages_total=0, freelist_pages=0, live_leaf_pages_scanned=0,
                 wal_frames_valid=0, wal_frames_stale=0, wal_final_pages=0,
                 deleted_in_wal=0, bytes_scanned=0, candidates=0,
                 duplicates_of_live=0, truncated=False, tables=[])

    try:
        fh = open(db_path, "rb")
    except OSError as exc:
        raise CarveError(f"Can't open database copy: {exc}") from exc
    with fh:
        hdr = _read_header(fh)
        if hdr["encoding"] not in (0, 1):
            res.warnings.append("Database text encoding is UTF-16; carving supports UTF-8 only.")
            res.stats = stats
            return res
        fh.seek(0, 2)
        ps = hdr["page_size"]
        npages = fh.tell() // ps
        stats["pages_total"] = npages
        usable = ps - hdr["reserved"]

        try:
            conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True)
            try:
                specs = build_specs(conn)
                live = _load_live(conn, specs)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise CarveError(f"Can't read the database schema ({exc}).") from exc
        if not specs:
            res.warnings.append("No recognisable browser tables (urls / downloads / cookies / logins / "
                                "moz_places / moz_cookies) were found in this database.")
            res.stats = stats
            return res
        stats["tables"] = [s.table for s in specs]

        ctx = _Ctx(specs, _ranges(), usable, time.monotonic() + max_seconds, max_scan_bytes)
        trunks, leaves = _walk_freelist(fh, hdr, npages)
        stats["freelist_pages"] = len(trunks) + len(leaves)
        if hdr["freelist_count"] and not (trunks or leaves):
            res.warnings.append("Freelist header is set but the freelist chain is unreadable/damaged.")

        for pgno in range(1, npages + 1):
            if not ctx.budget_ok():
                break
            fh.seek((pgno - 1) * ps)
            page = fh.read(ps)
            if len(page) < ps:
                break
            if pgno in leaves:
                _process_page(page, pgno, ctx, SRC_FREELIST, parse_cells=True, whole_page_scan_if_odd=True)
            elif pgno in trunks:
                # A trunk page keeps stale cell bytes after its pointer list.
                cnt = struct.unpack(">I", page[4:8])[0]
                _scan_region(page, min(8 + 4 * cnt, usable), usable, ctx, SRC_FREELIST, pgno)
            elif page[100 if pgno == 1 else 0] == 0x0D:
                stats["live_leaf_pages_scanned"] += 1
                _process_page(page, pgno, ctx, SRC_FREEBLOCK, parse_cells=False, whole_page_scan_if_odd=False)

        final_keys = set()
        pinned = []
        if wal_path and Path(wal_path).exists() and Path(wal_path).stat().st_size > 32:
            wps, frames = _index_wal(wal_path, res.warnings)
            if frames and wps != ps:
                res.warnings.append("The -wal page size differs from the database page size; WAL skipped.")
                frames = []
            # SQLite only trusts the contiguous run of salt-matching frames up to the
            # last commit frame; later frames are uncommitted tail or stale generations.
            last_commit, run_end = -1, -1
            for idx, (_off, _pg, valid, commit) in enumerate(frames):
                if not valid:
                    break
                run_end = idx
                if commit:
                    last_commit = idx
            final = {}
            for idx in range(last_commit + 1):
                final[frames[idx][1]] = frames[idx][0]
            stats["wal_final_pages"] = len(final)
            stats["wal_frames_valid"] = run_end + 1
            stats["wal_frames_stale"] = len(frames) - (run_end + 1)

            # (1) latest committed image of each page = the WAL's view of the database
            ctx.origin = "final"
            first_found = len(ctx.found)
            for pg, off in final.items():
                if not ctx.budget_ok():
                    break
                _process_page(_read_at(wal_path, off, ps), pg, ctx, SRC_WAL,
                              parse_cells=True, whole_page_scan_if_odd=False)
            final_keys = {r.exact for r in ctx.found[first_found:] if r.live_cell}

            # (2) rows the WAL's final page images no longer contain but the main file
            #     still does -> deleted inside the WAL (main-file parse still shows them)
            fh2 = open(db_path, "rb")
            try:
                for pg in final:
                    if pg > npages or not ctx.budget_ok():
                        continue
                    fh2.seek((pg - 1) * ps)
                    page = fh2.read(ps)
                    lay = _page_layout(page, 100 if pg == 1 else 0, usable) if len(page) == ps else None
                    if not lay:
                        continue
                    for spec, vals, rowid, ptr in _page_cells(page, pg, ctx, lay):
                        if not _validate(spec, vals, ctx.rng, False):
                            continue
                        norm = _normalize(spec, vals)
                        if norm["exact"] in final_keys:
                            continue
                        pinned.append(CarvedRecord(
                            kind=spec.kind, table=spec.table, browser=spec.browser, source=SRC_WAL,
                            confidence=CONF_HIGH, page_no=pg, offset=ptr, rowid=rowid,
                            primary=norm["primary"], secondary=norm["secondary"],
                            event_time=norm["event_time"], detail=dict(norm["detail"], deleted_in_wal=True),
                            status=ST_DELETED, ident=norm["ident"], exact=norm["exact"],
                            origin="main", pinned=True))
            finally:
                fh2.close()
            # (2b) pages the WAL's freelist now marks free although the main file still
            #      has them as live leaves. SQLite never rewrites a freed leaf page, so
            #      these pages never show up as WAL frames -- only the WAL's page 1 /
            #      trunk pages reveal them.
            def _main_page(pg):
                with open(db_path, "rb") as f3:
                    f3.seek((pg - 1) * ps)
                    return f3.read(ps)

            def _eff_page(pg):
                return _read_at(wal_path, final[pg], ps) if pg in final else _main_page(pg)

            if 1 in final and last_commit >= 0:
                eff_np = max(npages, frames[last_commit][3] or 0)
                eff_trunk = struct.unpack(">I", _eff_page(1)[32:36])[0]
                _et, eff_leaves = _walk_freelist_pages(_eff_page, eff_trunk, eff_np, usable)
                for pg in sorted(eff_leaves - trunks - leaves):
                    if pg > npages or pg in final or not ctx.budget_ok():
                        continue
                    page = _main_page(pg)
                    lay = _page_layout(page, 100 if pg == 1 else 0, usable) if len(page) == ps else None
                    if not lay:
                        continue
                    for spec, vals, rowid, ptr in _page_cells(page, pg, ctx, lay):
                        if not _validate(spec, vals, ctx.rng, False):
                            continue
                        norm = _normalize(spec, vals)
                        if norm["exact"] in final_keys:
                            continue
                        pinned.append(CarvedRecord(
                            kind=spec.kind, table=spec.table, browser=spec.browser, source=SRC_WAL,
                            confidence=CONF_HIGH, page_no=pg, offset=ptr, rowid=rowid,
                            primary=norm["primary"], secondary=norm["secondary"],
                            event_time=norm["event_time"], detail=dict(norm["detail"], deleted_in_wal=True),
                            status=ST_DELETED, ident=norm["ident"], exact=norm["exact"],
                            origin="main", pinned=True))
            stats["deleted_in_wal"] = len({(p.kind, p.exact) for p in pinned})

            # (3) older images inside the valid run, and stale-generation frames
            ctx.origin = "older"
            final_offsets = set(final.values())
            for idx, (off, pg, valid, _c) in enumerate(frames):
                if not ctx.budget_ok():
                    break
                if off in final_offsets and idx <= last_commit and final.get(pg) == off:
                    continue
                src = SRC_WAL if (valid and idx <= run_end) else SRC_WAL_STALE
                _process_page(_read_at(wal_path, off, ps), pg, ctx, src,
                              parse_cells=True, whole_page_scan_if_odd=False)
            res.warnings.append(
                "A -wal file was analysed. The standard artifact tables are parsed from the main "
                "database file only, so rows still pending in the WAL are shown here (status "
                "'wal_only' / 'deleted') rather than in the History/Cookies/Logins tables.")
        stats["bytes_scanned"] = ctx.scanned
        stats["truncated"] = ctx.truncated
        if ctx.truncated:
            res.warnings.append("Scan limit reached (size/time budget); results may be incomplete. "
                                "Re-run on a smaller copy or raise the limits in settings.")

    # -- classify against live rows, dedupe, order ------------------------
    best = {}
    for rec in pinned + ctx.found:
        exact_live, ident_live = live.get(rec.table, (set(), set()))
        if not rec.pinned:
            if rec.exact in exact_live:
                stats["duplicates_of_live"] += 1
                continue
            if rec.source in (SRC_WAL, SRC_WAL_STALE) and rec.origin != "final" and rec.exact in final_keys:
                continue   # older image of a row that still exists in the WAL's current view
            if rec.source == SRC_WAL and rec.origin == "final" and rec.live_cell:
                rec.status = ST_WAL_ONLY
            elif rec.ident in ident_live:
                rec.status = ST_OLDER
            else:
                rec.status = ST_DELETED
        key = (rec.kind, rec.exact)
        cur = best.get(key)
        if cur is None or rec.pinned or _CONF_RANK[rec.confidence] > _CONF_RANK[cur.confidence]:
            if cur is not None and cur.pinned:
                continue
            best[key] = rec
    res.records = sorted(best.values(),
                         key=lambda r: (r.event_time or datetime.min), reverse=True)
    stats["candidates"] = ctx.candidates
    res.stats = stats
    return res
