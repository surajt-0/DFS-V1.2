"""JSON API for the three recovery modules, all under /api/recovery/case/<id>/.

Access rules (same conventions as evidence/api.py):
  * reading      -> can view the case, and the plan has the feature (else 402)
  * running      -> plan not read-only, may upload evidence to the case, feature on
  * local DNS    -> additionally the deployment's local-scan switch + feature_local_scan
  * everything   -> written to the audit log
"""
from __future__ import annotations

from django.conf import settings
from django.db.models import Case as DCase, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.utils import log_action
from billing.access import has_feature, is_org_read_only, org_of
from billing.exceptions import PlanLimitExceeded
from cases.models import Case
from core.permissions import can_upload_evidence, require_upload_evidence, require_view
from evidence.models import EvidenceItem

from . import services
from .models import DnsEntry, RecoveredRecord, RecoveryRun, StateItem

FEATURE_RECOVERY = "feature_data_recovery"
FEATURE_DNS = "feature_dns_details"

LIMITATIONS = [
    "Deleted records are only recoverable while SQLite hasn't overwritten them: nothing is left after a "
    "VACUUM, with secure_delete enabled, or once later writes reuse the space.",
    "Every recovered row is labelled with where it was found and a confidence level. 'Low' means the record "
    "header was reconstructed from the table schema -- verify it before relying on it.",
    "Passwords and cookie values are never recovered or displayed; only site / name / timestamp metadata.",
    "A copy made while the browser was running may be missing its newest rows unless the -wal file was "
    "captured too; snapshot copies contain live rows only.",
]


class Pager(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _case_for_read(request, case_pk, feature):
    case = get_object_or_404(Case, pk=case_pk)
    require_view(request.user, case)
    org = org_of(request.user)
    if not has_feature(org, feature):
        raise PlanLimitExceeded("This feature isn't included on your current plan. Upgrade to unlock it.")
    return case


def _case_for_run(request, case_pk, feature):
    case = get_object_or_404(Case, pk=case_pk)
    require_view(request.user, case)
    org = org_of(request.user)
    if is_org_read_only(org):
        raise PlanLimitExceeded("The Free plan is view-only. Upgrade to run recovery.")
    if not has_feature(org, feature):
        raise PlanLimitExceeded("This feature isn't included on your current plan. Upgrade to unlock it.")
    require_upload_evidence(request.user, case)
    return case


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


# ---------------------------------------------------------------------------
# Shared filtered querysets (also used by the export downloads)
# ---------------------------------------------------------------------------
CONF_RANK = DCase(When(confidence="high", then=Value(3)), When(confidence="medium", then=Value(2)),
                  default=Value(1), output_field=IntegerField())
DELETED_SORTS = {"event_time", "kind", "source", "confidence", "primary", "status"}


def deleted_qs(request, case):
    qs = RecoveredRecord.objects.filter(evidence__case=case).select_related("evidence")
    g = request.GET
    for f in ("kind", "confidence", "source", "status"):
        if g.get(f):
            qs = qs.filter(**{f: g[f]})
    if g.get("evidence", "").strip().isdigit():
        qs = qs.filter(evidence_id=int(g["evidence"]))
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(primary__icontains=q) | Q(secondary__icontains=q))
    sort = g.get("sort", "-event_time")
    key = sort.lstrip("-")
    if key not in DELETED_SORTS:
        sort, key = "-event_time", "event_time"
    if key == "confidence":
        qs = qs.annotate(_rank=CONF_RANK).order_by(("-" if sort.startswith("-") else "") + "_rank", "id")
    else:
        qs = qs.order_by(sort, "id")
    return qs, sort


def state_qs(request, case):
    qs = StateItem.objects.filter(evidence__case=case).select_related("evidence")
    g = request.GET
    if g.get("category"):
        qs = qs.filter(category=g["category"])
    if g.get("status"):
        qs = qs.filter(status=g["status"])
    if g.get("evidence", "").strip().isdigit():
        qs = qs.filter(evidence_id=int(g["evidence"]))
    if g.get("dns") in ("1", "true"):
        qs = qs.filter(detail__dns=True)     # DoH / proxy / resolver-related browser settings
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(value__icontains=q))
    return qs.order_by("category", "-timestamp", "id")


def dns_qs(request, case):
    qs = DnsEntry.objects.filter(case=case).select_related("evidence")
    g = request.GET
    for f, col in (("type", "entry_type"), ("origin", "origin"), ("flag", "flag"), ("severity", "severity")):
        if g.get(f):
            qs = qs.filter(**{col: g[f]})
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(value__icontains=q))
    return qs.order_by("entry_type", "name", "id")


def _ev_name(e):
    return e.original_filename if e else ""


def ser_deleted(r):
    return {"id": r.id, "kind": r.kind, "browser": r.browser, "table": r.table_name, "source": r.source,
            "confidence": r.confidence, "status": r.status, "primary": r.primary, "secondary": r.secondary,
            "event_time": _iso(r.event_time), "detail": r.detail, "evidence_id": r.evidence_id,
            "evidence_name": _ev_name(r.evidence), "page_no": r.page_no, "offset": r.offset, "rowid": r.rowid}


def ser_state(i):
    return {"id": i.id, "category": i.category, "browser": i.browser, "name": i.name, "value": i.value,
            "timestamp": _iso(i.timestamp), "status": i.status, "source_file": i.source_file,
            "detail": i.detail, "evidence_id": i.evidence_id}


def ser_dns(d):
    return {"id": d.id, "origin": d.origin, "type": d.entry_type, "name": d.name, "value": d.value,
            "record_type": d.record_type, "ttl": d.ttl, "flag": d.flag, "severity": d.severity,
            "detail": d.detail, "observed_at": _iso(d.observed_at), "evidence_id": d.evidence_id,
            "evidence_name": _ev_name(d.evidence)}


def ser_domain(e):
    return {**e, "first_seen": _iso(e["first_seen"]), "last_seen": _iso(e["last_seen"])}


# ---------------------------------------------------------------------------
class SummaryAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, case_pk):
        case = get_object_or_404(Case, pk=case_pk)
        require_view(request.user, case)
        org = org_of(request.user)
        rec_on = has_feature(org, FEATURE_RECOVERY)
        dns_on = has_feature(org, FEATURE_DNS)
        read_only = is_org_read_only(org)
        can_run = (not read_only) and can_upload_evidence(request.user, case)

        carvable = []
        for ev in services.carvable_evidence(case):
            last = ev.recovery_runs.first()
            carvable.append({
                "id": ev.id, "original_filename": ev.original_filename,
                "evidence_type_display": ev.get_evidence_type_display(),
                "has_wal": services.companion_wal_path(ev) is not None,
                "snapshot_copy": "sqlite-snapshot" in (ev.note or ""),
                "last_run": None if not last else {
                    "status": last.status, "records_found": last.records_found, "created_at": _iso(last.created_at),
                    "warnings": last.warnings, "error": last.error, "stats": last.stats, "wal_used": last.wal_used},
            })
        by_conf = {r["confidence"]: r["n"] for r in
                   RecoveredRecord.objects.filter(evidence__case=case).values("confidence").annotate(n=Count("id"))}
        by_status = {r["status"]: r["n"] for r in
                     RecoveredRecord.objects.filter(evidence__case=case).values("status").annotate(n=Count("id"))}
        by_cat = {r["category"]: r["n"] for r in
                  StateItem.objects.filter(evidence__case=case).values("category").annotate(n=Count("id"))}
        closed = StateItem.objects.filter(evidence__case=case, status="recovered_closed").count()
        backup_only = StateItem.objects.filter(evidence__case=case, status="backup_only").count()
        dns_types = {r["entry_type"]: r["n"] for r in
                     DnsEntry.objects.filter(case=case).values("entry_type").annotate(n=Count("id"))}
        alerts = DnsEntry.objects.filter(case=case, severity="alert").count()
        return Response({
            "enabled": {"data_recovery": rec_on, "dns_details": dns_on},
            "read_only_plan": read_only, "can_run": can_run,
            "file_access": {"csv": has_feature(org, "feature_csv_export"),
                            "xlsx": has_feature(org, "feature_xlsx_export"),
                            "json": has_feature(org, "feature_json_export")},
            "local_dns_available": bool(settings.ENABLE_LOCAL_BROWSER_SCAN and has_feature(org, "feature_local_scan")),
            "carvable_evidence": carvable,
            "counts": {
                "deleted": {"total": sum(by_conf.values()), "by_confidence": by_conf, "by_status": by_status},
                "state": {"by_category": by_cat, "recovered_closed": closed, "backup_only": backup_only},
                "dns": {"by_type": dns_types, "alerts": alerts},
            },
            "limitations": LIMITATIONS,
        })


class CarveAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, case_pk):
        case = _case_for_run(request, case_pk, FEATURE_RECOVERY)
        ev_id = request.data.get("evidence_id")
        if ev_id not in (None, ""):
            try:
                targets = [get_object_or_404(case.evidence_items, pk=int(ev_id))]
            except (TypeError, ValueError):
                raise ValidationError({"evidence_id": ["Must be a whole number."]})
        else:
            targets = services.carvable_evidence(case)
        if not targets:
            raise ValidationError({"detail": "This case has no browser database evidence to recover from."})
        results = []
        for ev in targets:
            run = services.carve_evidence(ev, request.user)
            log_action(request, "recovery.carve",
                       f"{ev.original_filename}: {run.get_status_display()}, {run.records_found} record(s)"
                       f"{', WAL used' if run.wal_used else ''}", case=case)
            results.append({"evidence_id": ev.id, "filename": ev.original_filename, "status": run.status,
                            "records_found": run.records_found, "warnings": run.warnings, "error": run.error,
                            "stats": run.stats, "wal_used": run.wal_used})
        return Response({"results": results})


class _ListAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]
    feature = FEATURE_RECOVERY

    def paginate(self, request, seq, serializer):
        pg = Pager()
        page = pg.paginate_queryset(seq, request)
        resp = pg.get_paginated_response([serializer(x) for x in page])
        return resp


class DeletedListAPI(_ListAPI):
    def get(self, request, case_pk):
        case = _case_for_read(request, case_pk, self.feature)
        qs, sort = deleted_qs(request, case)
        resp = self.paginate(request, qs, ser_deleted)
        resp.data["sort"] = sort
        resp.data["evidence_options"] = [
            {"id": e.id, "original_filename": e.original_filename}
            for e in case.evidence_items.filter(id__in=RecoveredRecord.objects.filter(
                evidence__case=case).values_list("evidence_id", flat=True).distinct())]
        return resp


class StateListAPI(_ListAPI):
    def get(self, request, case_pk):
        case = _case_for_read(request, case_pk, self.feature)
        return self.paginate(request, state_qs(request, case), ser_state)


class DnsListAPI(_ListAPI):
    feature = FEATURE_DNS

    def get(self, request, case_pk):
        case = _case_for_read(request, case_pk, self.feature)
        return self.paginate(request, dns_qs(request, case), ser_dns)


class DnsDomainsAPI(_ListAPI):
    feature = FEATURE_DNS

    def get(self, request, case_pk):
        case = _case_for_read(request, case_pk, self.feature)
        rows = services.case_domains(case, q=request.GET.get("q", ""),
                                     only_recovered=request.GET.get("only_recovered") in ("1", "true"))
        return self.paginate(request, rows, ser_domain)


class DnsLocalScanAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, case_pk):
        case = _case_for_run(request, case_pk, FEATURE_DNS)
        if not settings.ENABLE_LOCAL_BROWSER_SCAN:
            raise PermissionDenied("Reading this computer's DNS state is disabled on this deployment. "
                                   "Upload a DNS export or hosts file instead.")
        if not has_feature(org_of(request.user), "feature_local_scan"):
            raise PlanLimitExceeded("Scanning this computer isn't included on your current plan. "
                                    "Upgrade to unlock it, or upload a DNS export instead.")
        res = services.scan_local_dns(case)
        log_action(request, "recovery.dns_local", f"Collected {res['stored']} DNS row(s) from this "
                   f"{res['platform']} machine", case=case)
        return Response(res)


class DnsLookupAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, case_pk):
        case = _case_for_run(request, case_pk, FEATURE_DNS)
        names = request.data.get("domains")
        if not isinstance(names, list) or not names or len(names) > 200 or \
                not all(isinstance(n, str) and len(n) <= 300 for n in names):
            raise ValidationError({"domains": ["Send a list of 1-200 domain names."]})
        if request.data.get("confirm") is not True:
            raise ValidationError({"confirm": ["Active lookups contact DNS servers; confirm to proceed."]})
        res = services.run_lookups(case, names)
        log_action(request, "recovery.dns_lookup",
                   f"Active DNS lookup of {res['looked_up']} domain(s), {res['records']} record(s) stored", case=case)
        return Response(res)


class DnsClearLookupsAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, case_pk):
        case = _case_for_run(request, case_pk, FEATURE_DNS)
        n, _ = DnsEntry.objects.filter(case=case, origin=DnsEntry.Origin.LOOKUP).delete()
        log_action(request, "recovery.dns_clear_lookups", f"Removed {n} active-lookup row(s)", case=case)
        return Response({"removed": n})
