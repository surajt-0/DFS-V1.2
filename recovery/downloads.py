"""Same-origin file downloads for the recovery tables (CSV / XLSX / JSON):
GET /recovery/case/<id>/<deleted|state|dns|domains>/?export=csv|xlsx|json[&filters]
Filters are identical to the JSON list endpoints, so an export always
matches what the examiner is looking at. Gated by the module's plan flag
AND the per-format export flags used everywhere else."""
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404

from auditlog.utils import log_action
from billing.access import has_feature, org_of
from cases.models import Case
from core.permissions import require_view
from evidence.table_config import EXPORT_FEATURE_MAP

from . import api, services
from .export import build_response, stamped

KINDS = {"deleted": api.FEATURE_RECOVERY, "state": api.FEATURE_RECOVERY,
         "dns": api.FEATURE_DNS, "domains": api.FEATURE_DNS}


def _rows(kind, request, case):
    if kind == "deleted":
        qs, _ = api.deleted_qs(request, case)
        hdr = ["Event time", "Type", "Browser", "Primary (URL/path/host)", "Secondary (title/name/user)",
               "Status", "Confidence", "Found in", "Evidence file", "Page", "Offset", "Rowid"]
        return hdr, ([r.event_time, r.kind, r.browser, r.primary, r.secondary, r.status, r.confidence,
                      r.source, r.evidence.original_filename, r.page_no, r.offset, r.rowid]
                     for r in qs.iterator(chunk_size=1000))
    if kind == "state":
        qs = api.state_qs(request, case)
        hdr = ["Category", "Browser", "Name / URL", "Value / title", "Time", "Status", "Source file", "Detail"]
        return hdr, ([i.category, i.browser, i.name, i.value, i.timestamp, i.status, i.source_file, i.detail]
                     for i in qs.iterator(chunk_size=1000))
    if kind == "dns":
        qs = api.dns_qs(request, case)
        hdr = ["Type", "Name", "Value", "Record type", "TTL", "Flag", "Severity", "Origin", "Evidence file",
               "Collected"]
        return hdr, ([d.entry_type, d.name, d.value, d.record_type, d.ttl, d.flag, d.severity, d.origin,
                      d.evidence.original_filename if d.evidence else "", d.observed_at]
                     for d in qs.iterator(chunk_size=1000))
    rows = services.case_domains(case, q=request.GET.get("q", ""),
                                 only_recovered=request.GET.get("only_recovered") in ("1", "true"))
    hdr = ["Domain", "Registrable domain", "Is IP", "Total mentions", "In live data", "In recovered data",
           "Only in recovered data", "First seen", "Last seen", "Seen in"]
    return hdr, ([r["domain"], r["registrable"], r["is_ip"], r["total"], r["live"], r["recovered"],
                  r["only_in_recovered"], r["first_seen"], r["last_seen"],
                  ", ".join(f"{k}: {v}" for k, v in r["sources"].items())] for r in rows)


def export_recovery(request, case_pk, kind):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    if kind not in KINDS:
        return HttpResponseBadRequest("Unknown recovery table.")
    fmt = request.GET.get("export", "")
    if fmt not in EXPORT_FEATURE_MAP:
        return HttpResponseBadRequest("Missing or unknown ?export= format (csv, xlsx, json).")
    case = get_object_or_404(Case, pk=case_pk)
    require_view(request.user, case)
    org = org_of(request.user)
    if not has_feature(org, KINDS[kind]):
        return JsonResponse({"detail": "This feature isn't included on your current plan."}, status=402)
    if not has_feature(org, EXPORT_FEATURE_MAP[fmt]):
        return JsonResponse({"detail": f"{fmt.upper()} export isn't included on your current plan."}, status=402)
    headers, rows = _rows(kind, request, case)
    log_action(request, "recovery.export", f"Exported {kind} ({fmt}) for case {case.case_number}", case=case)
    return build_response(fmt, headers, rows, stamped(f"{case.case_number}_recovered_{kind}"))
