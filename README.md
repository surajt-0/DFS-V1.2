# Digital Forensics Browser Suite -- Web Edition

A Django web application for examining browser artifacts (history, saved
logins, cookies, downloads, and cache metadata) across Chrome, Edge, Brave,
Opera, Firefox, and Safari -- built for **Agamya Cyber Tech** as the web
counterpart to the PySide6 desktop suite.

## Highlights

- **Case management** -- open/closed/archived cases, priority, tags, subject/
  custodian tracking, per-case activity.
- **Evidence intake** -- upload raw browser artifact files; every file is
  SHA-256 hashed on arrival and parsed against a safe **read-only copy**
  (original bytes are never reopened for writing).
- **Real parsers, not mockups** -- Chromium (History/Login Data/Cookies/
  Downloads), Firefox (places.sqlite/cookies.sqlite/logins.json), Safari
  (History.db), and cache archives (metadata-only zip scan).
- **Passwords & cookie values are never extracted in cleartext** -- the
  suite stores and displays `Protected` for these fields by design, not
  just UI masking.
- **Search / sort / paginate / export** on every artifact table, with CSV,
  XLSX, and JSON export that respects the current filter.
- **Chain-of-custody PDF report** per case (reportlab, no system deps).
- **Full audit trail** -- logins, uploads, parses, exports, and case
  changes are all logged and viewable/filterable in Session Logs.
- **Role-based access** -- Administrator (sees everything), Forensic
  Examiner (own cases only), Read-only Reviewer (view-only across all
  cases).
- **One-click synthetic demo case** -- populates every module with made-up
  data for training / UI walkthroughs, no real evidence needed.
- **Fully automated evidence intake** -- upload a whole batch of files at
  once (History, Login Data, Cookies, places.sqlite, a cache `.zip`, etc.)
  with no manual "what type is this" step; each file's artifact type is
  auto-detected from its content (`core/parsers/detect.py`), and anything
  unrecognized is flagged for a one-off manual reclassification rather than
  silently dropped or mis-filed.
- **One-click local machine scan** -- plan-gated (`feature_local_scan`),
  deployment-gated (`DFS_ENABLE_LOCAL_SCAN`, auto-on in the desktop build):
  finds every installed Chrome/Edge/Brave/Opera/Firefox/Safari profile on
  the machine running the app and ingests everything it can read
  automatically -- zero manual file picking for the common case. Only
  makes sense when the examiner's own workstation IS that machine (true
  for the desktop build), so it stays off by default on a shared/remote
  web deployment. Manual upload is always available as the fallback for
  anything it can't find or read (a locked file, an export handed over on
  removable media, a non-local deployment).
- **Deleted-data recovery** -- carves records a user deleted from Chromium/Firefox
  SQLite databases (history, downloads, cookies, login metadata) out of freed
  pages, in-page gaps and `-wal` files, each labelled with where it was found
  and a high/medium/low confidence. Passwords and cookie values are never
  recovered. See [RECOVERY.md](RECOVERY.md).
- **Browser system-data recovery** -- open tabs and **recently closed tabs**
  (Chromium SNSS + Firefox sessionstore), bookmarks incl. bookmarks that exist
  only in a backup, extensions, preferences (home page, DoH, proxy) and the
  hosts the browser talked to.
- **DNS details** -- hosts-file tampering checks, resolver config, DNS-cache
  exports (Windows/macOS/Linux), every domain in the case (incl. domains seen
  *only* in deleted data), and opt-in active lookups. Passive unless you ask.
- React SPA frontend (Vite + React Router), dark/light cybersecurity-suite theme with a toggle.
- **Desktop app** (Windows/macOS/Linux) -- the same app as a native window, no browser needed. See [DESKTOP.md](DESKTOP.md).

## Quick start

The client is a React SPA (`frontend/`); Django is the API + admin only (see
[React frontend](#react-frontend) below for the full picture). Two ways to
run it locally:

**Dev mode (recommended while working on the frontend) -- two processes:**

```bash
python3 -m venv venv
source venv/bin/activate          # venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env               # edit as needed; safe dev defaults if you skip this
export $(grep -v '^#' .env | xargs)  # or use django-environ / your process manager

python manage.py migrate
python manage.py seed_plans          # creates the Free / Pro / Enterprise plans
python manage.py createsuperuser
python manage.py runserver           # Django on :8000
```

```bash
cd frontend
npm install
npm run dev                          # Vite on :5173, proxies /api etc. to :8000
```

Visit `http://127.0.0.1:5173/` and sign up (creates your organization on the
Free plan) or sign in. Use **Load Demo Case** from the dashboard to explore
every module immediately with synthetic data.

**Single-origin mode (closer to production) -- one process:**

```bash
cd frontend && npm install && npm run build && cd ..
python manage.py runserver
```

Django now serves the built SPA directly at `http://127.0.0.1:8000/`
(`dfs_web/spa.py`) -- no separate frontend server needed. Rerun
`npm run build` after any frontend change.

**Desktop app -- one native window, no browser:**

```bash
python desktop_app.py
```

Same idea as single-origin mode, but opened in a native OS window instead of
a browser tab, with the database/evidence storage automatically pointed at a
per-user data directory instead of the project folder. See
[DESKTOP.md](DESKTOP.md) for packaging it into a standalone
`.exe`/`.app`/Linux binary.

### Who can upload evidence

On **Pro and Enterprise**, every role in the organization -- administrator,
forensic examiner, and read-only reviewer -- can add evidence to any case
they can see, both by manual upload and via the automatic local scan.
Editing or deleting a case, changing its status, and removing/reparsing
evidence remain restricted to the case's editors (admins/owners, or the
assigned examiner). The **Free** plan is view-only for every role.
Set `DFS_EVIDENCE_UPLOAD_ALL_ROLES=False` to require edit rights for
uploads instead (see `core/permissions.py::can_upload_evidence`).

## Enterprise / subscription features

Every signup creates a new **Organization** (tenant); the signer-upper is
its owner/admin. Cases, evidence, and audit-log visibility are all scoped to
the caller's organization -- no cross-tenant data is ever visible, regardless
of role.

Three plans ship by default (`billing/management/commands/seed_plans.py`),
fully editable from `/admin/`. Plans are tiered purely by **case volume and
feature flags** -- there is no seat/team concept; every organization is
single-owner:

| | Free | Pro | Enterprise |
|---|---|---|---|
| Cases (monthly billing) | 3 | 25 | Unlimited |
| Cases (yearly billing) | 3 | **35** (25 + 10 bonus) | Unlimited |
| Evidence/case | 5 | 50 | Unlimited |
| Access | **View-only** (no create/edit) | Full | Full |
| CSV export | -- | Yes | Yes |
| XLSX / JSON export | -- | Yes | Yes |
| Chain-of-custody PDF reports | -- | Yes | Yes |
| Full org-wide audit log | -- | Yes | Yes |
| Local workstation scan | -- | Yes | Yes |
| Priority support / custom branding / SSO | -- | -- | Yes |

Yearly-billed organizations get a **bonus case allowance** on top of the
plan's base `max_cases` (`Plan.yearly_case_bonus`, editable per plan from
`/billing/admin/plans/` or the React Admin Plans screen) -- a small reward
for committing annually. `Plan.max_cases_for(cycle)` / `billing.access.
limit_status(org, "cases")` compute the effective limit from the org's live
`Subscription.billing_cycle`, so switching an org between monthly and yearly
billing changes its case ceiling immediately, with no extra code path.
Downgrading a plan or reducing its limit **never locks out existing
cases** -- it only blocks creating new ones once the org is at/over the new
limit (`is_org_read_only` / `limit_status(...).allowed` gate creation only;
`require_view`/`can_view_case` never consult the plan limit).

Free-tier organizations are strictly read-only (`Plan.is_read_only`) --
case and evidence creation/editing is blocked regardless of the member's
role, until the org upgrades.

Key routes:

- `/billing/pricing/` -- plan comparison + upgrade CTAs
- `/billing/checkout/<plan_key>/<monthly|yearly>/` -- Razorpay checkout (org owner only)
- `/billing/checkout/<payment_id>/verify/` -- payment verification callback
- `/billing/my/` -- current plan, usage vs. limits, invoice history
- `/billing/my/modify/` -- change plan/cycle
- `/billing/my/cancel/` -- cancel subscription (reverts to Free at period end)
- `/billing/my/downgrade-free/` -- immediate downgrade to Free
- `/billing/admin/plans/` -- edit plan limits/pricing/features (admin only)
- `/billing/webhook/razorpay/` -- `payment.captured` / `payment.failed` webhook

**Payments run through Razorpay** (`billing/razorpay_client.py`). Set
`DFS_RAZORPAY_KEY_ID` / `DFS_RAZORPAY_KEY_SECRET` (see `.env.example`) for
live payments; leave them blank to run in **demo mode**, where the entire
checkout -> invoice -> plan-activation flow works locally without a real
gateway (every simulated payment is flagged `is_demo=True` and labelled in
the UI, so it's never mistaken for real revenue). An optional webhook
endpoint (`/billing/webhook/razorpay/`) is included for `payment.captured` /
`payment.failed` events if you configure one in the Razorpay dashboard.

Feature/limit enforcement lives centrally in `billing/access.py` and is
applied via decorators (`@require_feature`, `@require_case_slot`) and inline
checks (`evidence_limit_status`) in the `cases` and `evidence` views --
new limits or flags only need a field on `Plan`, not scattered code changes.
The same `billing.access` functions back the JSON API (see below), so the
enforcement never drifts between the server-rendered pages and the SPA.

## React frontend

`frontend/` is the **entire client-facing surface** of this application --
a full React SPA (Vite + React Router, no server-rendered templates) that
covers auth, dashboard, cases, evidence upload/parsing, artifact tables,
audit log, profile, and the full billing flow (pricing, checkout,
subscription management, admin plan editor). The old Django template views
that used to render server-side pages for the same features have been
removed entirely -- keeping two independent UIs in sync with the same
permission/billing-limit logic long-term was a needless source of drift, so
there is now exactly one client. What's left on the Django side is:
`/api/...` (JSON, consumed by the SPA), `/admin/` (Django admin, an
internal/staff tool), `/evidence/case/<id>/<table>/?export=...` (same-origin
file-download links the SPA points to, see below), and
`/billing/webhook/razorpay/` (server-to-server, not a page).

The SPA talks to Django exclusively over JSON under `/api/...`, using the
normal Django session cookie for auth (no separate token system) --
`POST /api/accounts/login/` sets the cookie, every other call picks it up
automatically via `credentials: 'include'`, and state-changing requests
carry the `X-CSRFToken` header read from the `csrftoken` cookie.

Run it alongside Django:

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173, proxies /api and /evidence to :8000
```

`npm run build` produces a static `dist/` that Django serves directly in
production via `dfs_web/spa.py` (see Quick start above) -- or you can point
any static host/CDN at it instead and set `CORS_ALLOWED_ORIGINS`/
`CSRF_TRUSTED_ORIGINS` to match.

**API surface** (all JSON, session-cookie authenticated):

| App | Endpoints |
|---|---|
| `accounts` | `POST /api/accounts/signup/`, `/login/`, `/logout/`; `GET/PATCH /api/accounts/profile/`; `POST /api/accounts/password-change/` |
| `billing` | `GET /api/billing/me/`, `/plans/`, `/my/`, `/payments/`; `POST /my/modify/`, `/my/cancel/`, `/my/downgrade-free/`, `/checkout/<plan_key>/<cycle>/`, `/checkout/<payment_id>/verify/`; admin: `GET/PATCH /admin/plans/[<id>/]` |
| `cases` | `GET/POST /api/cases/` (search `q`, `status`, pagination); `GET/PATCH/DELETE /api/cases/<id>/`; `POST /api/cases/<id>/status/<status>/`; `GET /api/cases/<id>/report/` (PDF) |
| `evidence` | `POST /api/evidence/case/<case_id>/upload/` (multipart); `GET/DELETE /api/evidence/<id>/`; `POST /api/evidence/<id>/reparse/`; `POST /api/evidence/demo-case/`; `GET /api/evidence/case/<case_id>/table/<history\|login\|cookie\|download\|cache>/` |
| `auditlog` | `GET /api/audit/` (search `q`, `action`, pagination) |
| `dashboard` | `GET /api/dashboard/stats/` |

Exports (CSV/XLSX/JSON) and case PDF reports stay on file-download GETs --
exports use dedicated same-origin `/evidence/case/<id>/<history\|logins\|
cookies\|downloads\|cache>/?export=<csv\|xlsx\|json>` endpoints
(`evidence/downloads.py` + `evidence/download_urls.py`; the session cookie
is enough for the browser to download the file directly, no reason to
reinvent that as a JSON call), while the case PDF report has a dedicated
`/api/cases/<id>/report/` endpoint. Every endpoint above enforces the same
plan-based access control: `billing.access.
is_org_read_only` blocks case/evidence creation on the Free plan,
`limit_status`/`evidence_limit_status` enforce the case-volume (cycle-aware,
see the yearly bonus above) and per-case evidence-volume limits, and
`has_feature` gates each export format, PDF reports, and org-wide audit
visibility.

**Status codes**: the JSON API distinguishes *why* a request was blocked --
- **402 Payment Required** (`billing.exceptions.PlanLimitExceeded`) -- the
  caller's **plan** doesn't allow this: case/evidence limit reached, the
  Free tier's view-only restriction, or a gated feature (PDF reports,
  an export format, audit-log access) not included on the current plan.
- **403 Forbidden** (DRF's standard `PermissionDenied`) -- the caller's
  **role** doesn't allow this regardless of plan: a Read-only Reviewer
  trying to create/edit, someone outside their organization, or a non-owner
  trying to manage billing.

Both carry a human-readable `detail` message the SPA surfaces inline (see
`PlanLimitNotice` / `Banner` in `frontend/src/components/`), so the UI reads
the same either way -- the status code is there for programmatic callers
(and to make "upgrade your plan" vs. "you don't have permission" easy to
tell apart in monitoring/logs).

## Typical workflow

1. **Create a case** -- name, subject/custodian, priority, tags.
2. **Add evidence** -- pick the artifact type and upload the raw file. It is
   hashed and parsed automatically.
3. **Investigate** -- open a module (History / Logins / Cookies / Downloads
   / Cache), search, sort, filter by evidence file, export to CSV/XLSX/JSON.
4. **Report** -- generate the chain-of-custody PDF from the case page.
5. **Review the audit trail** -- Session Logs shows every action taken in
   the case, by whom, and when.

## Where files typically live for each artifact type

| Browser | History | Logins | Cookies |
|---|---|---|---|
| Chrome/Edge/Brave/Opera | `.../User Data/Default/History` | `.../User Data/Default/Login Data` | `.../User Data/Default/Cookies` |
| Firefox | `.../Profiles/xxx.default/places.sqlite` | `.../Profiles/xxx.default/logins.json` | `.../Profiles/xxx.default/cookies.sqlite` |
| Safari (macOS) | `~/Library/Safari/History.db` | -- | -- |

These files usually have **no extension** for Chromium (`History`,
`Login Data`, `Cookies`) -- that's expected, just select the matching
evidence type on upload.

## Production notes

- Set `DFS_SECRET_KEY`, `DFS_DEBUG=False`, `DFS_ALLOWED_HOSTS`, and put this
  behind HTTPS (`DFS_SECURE_SSL_REDIRECT=True`, `DFS_SECURE_COOKIES=True`)
  before exposing it beyond localhost.
- The bundled SQLite database is fine for small teams; for larger
  deployments point `DATABASES` in `dfs_web/settings.py` at PostgreSQL.
- `EVIDENCE_STORAGE_ROOT` (via `DFS_EVIDENCE_ROOT`) should be a disk with
  enough space and a backup policy -- this is where every uploaded evidence
  file and safe working copies live.
- Run `python manage.py collectstatic` behind a real web server (nginx/
  Apache) or a WSGI host that serves `/static/` in production; `runserver`
  is dev-only.
- Consider fronting with Gunicorn/uWSGI + nginx, e.g.
  `gunicorn dfs_web.wsgi:application --bind 0.0.0.0:8000`.

## Project layout

```
dfs_web/             Django project settings/urls, spa.py (serves the built React app)
accounts/             Roles (admin/examiner/viewer), signup/login/profile -- API only (accounts/api.py)
core/                 Parsers, safe-copy/hash utilities, permissions, browser_detect
  core/recovery/        Pure-Python engines: SQLite carver, browser-state parsers, LZ4/mozLz4 reader
  core/dnsintel/        Pure-Python DNS engines: hosts/resolver/cache parsers, lookups, domain utils
cases/                Case model, JSON API (cases/api.py), PDF report generation
evidence/             Upload, parsing dispatch, artifact-table API, CSV/XLSX/JSON export downloads
recovery/             Deleted-data / browser system-data / DNS modules: models, services, JSON API, exports
auditlog/              Immutable audit trail, JSON API
dashboard/            Overview / stats API
billing/              Plans, Organizations (tenants), Subscriptions, Razorpay checkout + webhook
frontend/             React SPA (Vite + React Router) -- the entire client-facing UI
static/               Logo/media assets referenced by the SPA build; no template CSS/JS anymore
desktop_app.py        Desktop launcher (pywebview + waitress) -- see DESKTOP.md
desktop/build.spec    PyInstaller spec for packaging desktop_app.py into a standalone executable
.github/workflows/    CI: builds Windows/macOS/Linux desktop binaries via GitHub Actions
```

There is intentionally no `templates/` directory and no server-rendered
views (`cases/views.py`, `billing/views.py`, etc.) -- see the React
frontend section above for why.
