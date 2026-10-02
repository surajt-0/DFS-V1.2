# Deleted-data recovery, browser system data & DNS details

Three modules added to the suite. All of them work on a **temporary copy**
of your evidence (the stored file is never opened for writing -- the tests
assert its SHA-256 is unchanged), are plan-gated, permission-checked,
audit-logged, and exportable (CSV / XLSX / JSON).

| Module | Plan flag | Where |
|---|---|---|
| Deleted data + Browser system data | `feature_data_recovery` | Case page -> *Deleted data* / *Browser system data* |
| DNS details | `feature_dns_details` | Case page -> *DNS details* |

Both flags are on for Pro and Enterprise (the `billing/0005` migration turns
them on for existing installs) and can be changed in **Manage plans** or
`/admin/`. Running a recovery needs the same right as uploading evidence;
reading results needs only access to the case.

## 1. Deleted data (SQLite carving)

**How it works.** SQLite doesn't wipe a row when it is deleted. The carver
(`core/recovery/sqlite_carver.py`) reads the database copy and inspects:

| Found in | Meaning |
|---|---|
| `freelist_page` | a whole page freed by a bulk delete, old cells intact |
| `freeblock` | a deleted cell inside a page that still has live rows, or the unused gap |
| `wal` | the `-wal` file: rows **deleted in the WAL**, rows that exist only in the WAL (not yet checkpointed), older page images |
| `wal_stale` | frames left from an earlier WAL generation |

Supported tables: Chromium `urls`, `downloads`, `cookies`, `logins`; Firefox
`moz_places`, `moz_cookies`. Every candidate is validated against the live
table schema and strict plausibility checks (URL scheme, timestamp range,
column types), so random bytes don't become fake evidence.

**Confidence** -- *high*: complete cell whose stored length matches the size
computed from its own record header. *medium*: decoded and validated, part of
the header rebuilt from the schema. *low*: two header bytes rebuilt on an
assumption -- a lead to verify, not proof.

**Status** -- *Deleted* (no live row matches), *Older version* (the record
was later updated; this is the earlier state), *Only in WAL*.

**Getting the WAL.** Upload `History-wal` (etc.) next to `History` in the same
case, or use *Scan this computer* -- it copies the `-wal` next to its copy of
the database and records the WAL's SHA-256 in the evidence note. A copy made
with SQLite's snapshot fallback (browser had the file locked) contains only
live rows; the UI flags that.

**Privacy guarantee.** Only a fixed whitelist of metadata columns is decoded.
`password_value`, cookie `value` and `encrypted_value` are not on it, cannot be
returned, and are covered by tests that plant secret strings and assert they
never appear in any output.

**Limits (shown in the UI too).** Nothing is recoverable after `VACUUM`, with
`secure_delete` on, or once freed space was reused. Records whose payload
spilled onto overflow pages, UTF-16 databases and Safari's schema are skipped.
WAL frame checksums are not verified. Scans are bounded (64 MB of byte-scanned
space / 180 s per file) and report when they hit the bound.

## 2. Browser system data

Upload the files, or tick **Also collect browser system data** on the scan
page (each file counts toward the case's evidence limit).

| Category | Files |
|---|---|
| Tabs & sessions | Chromium `Current Session`, `Last Session`, `Current Tabs`, `Last Tabs`, `Session_*`, `Tabs_*`; Firefox `recovery.jsonlz4`, `recovery.baklz4`, `previous.jsonlz4`, `sessionstore.jsonlz4` (**includes recently closed tabs/windows**) |
| Bookmarks | `Bookmarks`, `Bookmarks.bak`, Firefox `bookmarks-*.jsonlz4` -- bookmarks present in a backup but missing from the current copy are marked *Only in a backup (deleted since)* |
| Extensions | Firefox `extensions.json`; Chromium extensions from `Preferences` |
| Preferences | Chromium `Preferences` / `Secure Preferences` / `Local State`, Firefox `prefs.js` (home page, downloads folder, signed-in account, proxy, DNS-over-HTTPS) |
| Network state | Chromium `Network Persistent State` (hosts contacted) |

## 3. DNS details

* **Uploaded evidence** -- a `hosts` file, or a text export of the DNS cache /
  resolver config (`ipconfig /displaydns`, `scutil --dns`, `resolvectl status`,
  `resolv.conf`) is auto-detected and parsed.
* **Hosts-file checks** -- a well-known domain (banks, Microsoft/Google/Apple,
  AV vendors, ...) mapped to a non-local address is an **alert** (possible
  redirect/phishing); a well-known domain blackholed to loopback is a **warning**
  (possible blocking of updates/security); ordinary ad-block entries are info.
* **Collect from this computer** -- desktop build / `DFS_ENABLE_LOCAL_SCAN`
  only. Reads the hosts file and resolver settings, plus the DNS client cache on
  Windows. (macOS/Linux don't expose a readable system DNS cache.)
* **Domains in this case** -- every host in history, downloads, cookies, login
  origins, sessions, bookmarks, network state **and recovered records**, with
  live-vs-recovered counts; domains that appear *only* in deleted data are
  highlighted.
* **Active lookups** -- the only network traffic in the suite, and only when you
  select domains and confirm. Results are labelled with their lookup time and
  describe DNS *today*, not at the time of the events. Install `dnspython`
  for NS/MX/TXT/CNAME records; without it you get A/AAAA from the OS resolver.

## API

All under `/api/recovery/case/<id>/` (session auth + CSRF like the rest of the API):

```
GET  summary/                 capabilities, evidence list (WAL present?), counts, limitations
POST carve/                   {"evidence_id": optional}   run recovery
GET  deleted/   state/        ?q &kind &confidence &source &status &evidence &category &sort &page
GET  dns/entries/  dns/domains/   ?q &type &severity &origin &only_recovered &page
POST dns/scan-local/          collect from this computer
POST dns/lookup/              {"domains": [...], "confirm": true}
POST dns/clear-lookups/
```

Downloads: `GET /recovery/case/<id>/<deleted|state|dns|domains>/?export=csv|xlsx|json`
(same filters as the lists; text cells are neutralised against spreadsheet
formula injection, since recovered data is untrusted input).

## Tests

`python manage.py test` -- `recovery/tests.py` drives the real upload pipeline
and real SQLite/WAL files end to end; `core/tests_carver.py` covers every
supported schema, the no-secrets guarantee and corrupted/hostile input;
`core/tests_mozlz4.py` has known-answer vectors for the LZ4 decoder.

## Files added / changed

New: `core/recovery/`, `core/dnsintel/`, `recovery/` (app), `frontend/src/pages/Recovery.jsx`,
`frontend/src/pages/recovery/`, `RECOVERY.md`.
Changed: `evidence/` (two new evidence types, parse dispatch, local scan captures
`-wal` + optional system data), `core/parsers/detect.py`, `core/browser_detect.py`,
`billing/` (two plan flags + migration), `cases/report.py` (report section),
`dfs_web/{settings,urls}.py`, `desktop/build.spec`, frontend routing/API client/CSS.

**Also fixed (pre-existing):** content-type sniffing opened stored evidence
without `immutable=1`, which made SQLite create empty `-wal`/`-shm` files next
to a WAL-mode database. It no longer touches the evidence directory.
