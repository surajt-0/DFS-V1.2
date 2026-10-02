"""Serves the built React SPA from Django.

In dev you normally run the Vite dev server (`npm run dev`, :5173) which
proxies /api etc. to Django (:8000) -- see frontend/vite.config.js. This
module is for the *other* deployment shape described in the README:
`npm run build` once, then Django serves the resulting frontend/dist/
directly, so the whole thing is a single origin/process in production
(no separate nginx/CDN required, though you can still put one in front).

Any path not matched by /admin/, /api/, /evidence/ (downloads), or
/billing/webhook/ falls through to serve_spa() here (see dfs_web/urls.py's
catch-all), returning index.html so React Router can take over client-side
routing -- including on a hard refresh of a deep link like /cases/42.
"""
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views.static import serve

FRONTEND_DIST = Path(settings.BASE_DIR) / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"

_NOT_BUILT_MESSAGE = """
<!doctype html><html><body style="font-family:sans-serif;padding:40px;max-width:640px;margin:auth">
<h2>Frontend isn't built yet</h2>
<p>Django can't find <code>frontend/dist/index.html</code>.</p>
<p>For local development, run the Vite dev server instead of hitting this Django port directly:</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run dev</pre>
<p>...and browse <code>http://localhost:5173</code>, which proxies API calls here.</p>
<p>To have Django itself serve the built app (single-origin/production mode), build it first:</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>
</body></html>
"""


def serve_spa(request, _unused=None):
    # Built assets (frontend/dist/assets/...) referenced by index.html at
    # the site root -- served directly rather than through STATIC_URL,
    # since Vite's default build already fingerprints filenames for
    # long-lived caching.
    path = request.path.lstrip("/")
    if path.startswith("assets/") and (FRONTEND_DIST / path).is_file():
        return serve(request, path, document_root=str(FRONTEND_DIST))

    if not INDEX_HTML.exists():
        return HttpResponseNotFound(_NOT_BUILT_MESSAGE)
    return HttpResponse(INDEX_HTML.read_text(encoding="utf-8"))
