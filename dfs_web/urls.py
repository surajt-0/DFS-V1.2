"""
Client-facing surface: the React SPA only.

- /admin/          Django admin (internal/staff tool, not a client UI)
- /api/...         JSON API consumed by the SPA (and nothing else)
- /billing/webhook/razorpay/   server-to-server Razorpay callback, not a page
- everything else  falls through to the built SPA (frontend/dist/index.html)
                    so React Router can handle client-side routes like
                    /cases/42 directly, including on a hard refresh.

The old server-rendered template views (cases/evidence/billing/accounts/
dashboard/auditlog "views.py") have been removed -- they were an earlier,
parallel implementation of the same features that the API + SPA superseded.
Keeping both around risked the two UIs drifting out of sync with each
other's permission/limit logic, so there is now exactly one client surface.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from .spa import serve_spa

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/billing/", include("billing.api_urls")),
    path("api/accounts/", include("accounts.api_urls")),
    path("api/cases/", include("cases.api_urls")),
    path("api/evidence/", include("evidence.api_urls")),
    path("api/recovery/", include("recovery.api_urls")),
    path("api/audit/", include("auditlog.api_urls")),
    path("api/dashboard/", include("dashboard.api_urls")),

    # Legacy same-origin file-download endpoints the SPA still links to
    # directly (CSV/XLSX/JSON exports) -- see evidence/api_urls.py's
    # module docstring / README for why these stay outside /api/.
    path("evidence/", include("evidence.download_urls")),
    path("recovery/", include("recovery.download_urls")),

    # Server-to-server only (Razorpay dashboard webhook config), not a page.
    path("billing/", include("billing.urls")),

    # Everything else: hand off to the built React app. Must stay last.
    path("", serve_spa, name="spa_index"),
    path("<path:_unused>", serve_spa, name="spa_catchall"),
]

admin.site.site_header = f"{settings.SUITE_NAME} Administration"
admin.site.site_title = settings.SUITE_ORG
admin.site.index_title = "Suite Administration"
