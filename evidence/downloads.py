"""File-download endpoints for artifact table exports (CSV/XLSX/JSON).

These stay outside /api/ deliberately: they're plain GETs that trigger a
browser file download, not JSON calls -- the same Django session cookie
that authenticates the SPA's fetch() calls is enough for the browser to
authenticate a direct link/window.open() to one of these URLs, so there's
no reason to reinvent file downloads as a JSON API response. The React SPA
links to these via `evidenceApi.exportUrl()` (frontend/src/api/client.js).

This is the only surviving piece of the old evidence/views.py (a much
larger file that also server-rendered the HTML artifact tables themselves
-- that part is superseded by evidence/api.py's ArtifactTableAPI + the
React ArtifactTable page, so it was removed along with the other
template views).
"""
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404

from billing.access import has_feature, org_of
from cases.models import Case
from core.permissions import require_view

from .export import EXPORTERS, stamped_filename
from .table_config import EXPORT_FEATURE_MAP, SORT_WHITELIST, TABLE_CONFIG


def export_table(request, case_pk, kind):
    """GET /evidence/case/<case_pk>/<kind>/?export=csv|xlsx|json[&q=...&sort=...&evidence=...]"""
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    if kind not in TABLE_CONFIG:
        return HttpResponseBadRequest("Unknown artifact table.")
    export = request.GET.get("export", "")
    if export not in EXPORTERS:
        return HttpResponseBadRequest("Missing or unknown ?export= format (csv, xlsx, json).")

    case = get_object_or_404(Case, pk=case_pk)
    require_view(request.user, case)

    needed_feature = EXPORT_FEATURE_MAP.get(export)
    if needed_feature and not has_feature(org_of(request.user), needed_feature):
        return JsonResponse(
            {"detail": f"{export.upper()} export isn't included on your current plan. Upgrade to unlock it."},
            status=402,
        )

    cfg = TABLE_CONFIG[kind]
    # Same reasoning as evidence/api.py's ArtifactTableAPI: the child model
    # is the discriminator now, not the parent evidence item's declared type.
    qs = cfg["model"].objects.filter(evidence__case=case).select_related("evidence")

    evidence_filter = request.GET.get("evidence", "").strip()
    if evidence_filter:
        qs = qs.filter(evidence_id=evidence_filter)

    q = request.GET.get("q", "").strip()
    if q:
        cond = Q()
        for f in cfg["search_fields"]:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)

    sort = request.GET.get("sort", cfg["default_sort"])
    if sort.lstrip("-") not in SORT_WHITELIST:
        sort = cfg["default_sort"]
    qs = qs.order_by(sort, "id")

    from auditlog.utils import log_action
    log_action(request, "evidence.export", f"Exported {kind} table ({export}) for case {case.case_number}", case=case)

    filename = stamped_filename(f"{case.case_number}_{kind}")
    return EXPORTERS[export](qs, cfg["export_fields"], cfg["export_headers"], filename)
