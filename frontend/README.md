# Billing SPA (React frontend)

A React app for the subscription system already modeled in `billing/` (case-volume-based plans,
monthly/yearly pricing, per-plan file-access flags). It talks to a new JSON API that sits
alongside the existing server-rendered `billing/` pages -- nothing in the old templates/views was
removed, so `/billing/pricing/`, `/billing/my/`, etc. still work as before.

## What it adds

**Backend** (`billing/serializers.py`, `billing/api.py`, `billing/api_urls.py`, mounted at
`/api/billing/`):

| Endpoint | Who | Purpose |
|---|---|---|
| `GET /api/billing/plans/` | anyone | Pricing-page data |
| `GET /api/billing/me/` | anyone | Current user/org/role |
| `GET /api/billing/my/` | logged in | Dashboard: plan, usage, payments |
| `POST /api/billing/checkout/<plan>/<cycle>/` + `.../verify/` | org owner | Razorpay checkout (demo mode if no keys set) |
| `POST /api/billing/my/modify/`, `/cancel/`, `/downgrade-free/` | org owner | Self-service plan changes |
| `GET/PATCH /api/billing/admin/plans/`, `/admin/plans/<id>/` | superuser | **Edit price (monthly/yearly), max cases, max evidence/case, and every file-access flag per plan** |

Auth is the same Django session cookie used everywhere else on the site -- log in at
`/accounts/login/` and the SPA picks it up automatically. Admin edits are audit-logged exactly
like the old `manage_plans` view.

**Frontend** (`frontend/`, Vite + React + react-router):

- `/pricing` -- public plan cards, monthly/yearly toggle, file-access badges, subscribe flow
- `/checkout/:planKey/:cycle` -- Razorpay Checkout.js (or a "simulate payment" button in demo mode)
- `/dashboard` -- current plan, case-usage bar, payment history, cancel
- `/admin/plans` -- superuser-only: editable price/case-limit/file-access controls per plan

## Running it locally

```bash
# Backend (from the repo root)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_plans        # creates Free / Pro / Enterprise
python manage.py createsuperuser
python manage.py runserver         # http://127.0.0.1:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

The Vite dev server proxies `/api`, `/accounts`, and `/static` to `127.0.0.1:8000` (see
`frontend/vite.config.js`), so open `http://localhost:5173/pricing` and log in through the normal
Django login page -- no separate frontend auth to configure.

## Production build

```bash
cd frontend
npm run build       # outputs frontend/dist
```

Serve `frontend/dist` from whatever static host/CDN you like, or point Django's `STATICFILES_DIRS`
at it and serve it from the same domain as the API to avoid CORS entirely. If you do serve it from
a different origin, add that origin to `DFS_CORS_ALLOWED_ORIGINS` and
`DFS_CSRF_TRUSTED_ORIGINS` in your environment.
