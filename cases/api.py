from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.utils import log_action
from billing.access import is_org_read_only, limit_status, org_of
from billing.exceptions import PlanLimitExceeded
from core.permissions import require_edit, require_view, visible_cases_qs

from .models import Case
from .report import build_case_report_pdf
from .serializers import CaseDetailSerializer, CaseListSerializer, CaseWriteSerializer


class CasePagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


def _check_case_slot(request):
    """Mirrors billing.access.require_case_slot but returns a DRF 402
    (plan restriction, not a role/permission one) instead of a redirect,
    for use from JSON endpoints."""
    org = org_of(request.user)
    if is_org_read_only(org):
        raise PlanLimitExceeded(
            "The Free plan is view-only. Upgrade to create or edit cases."
        )
    usage = limit_status(org, "cases")
    if not usage["allowed"]:
        raise PlanLimitExceeded(
            f"Your plan allows {usage['limit']} case(s) and you're at the limit. Upgrade to open more."
        )


class CaseListCreateAPI(APIView):
    """GET /api/cases/ -- list (search + status filter + pagination) plus
    case_usage so the SPA can grey out / explain the 'New case' button.
    POST /api/cases/ -- create, enforcing the plan's case-volume limit."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CasePagination

    def get(self, request):
        qs = visible_cases_qs(request.user, Case.objects.select_related("investigator"))

        q = request.GET.get("q", "").strip()
        status_filter = request.GET.get("status", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(case_number__icontains=q) |
                Q(subject_name__icontains=q) | Q(tags__icontains=q)
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        data = CaseListSerializer(page, many=True).data
        response = paginator.get_paginated_response(data)
        response.data["case_usage"] = limit_status(org_of(request.user), "cases")
        response.data["statuses"] = Case.Status.choices
        response.data["is_read_only"] = is_org_read_only(org_of(request.user))
        response.data["can_create"] = not request.user.profile.is_viewer_role
        return response

    def post(self, request):
        if request.user.profile.is_viewer_role:
            raise PermissionDenied("Read-only reviewers cannot create cases.")
        _check_case_slot(request)

        serializer = CaseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = serializer.save(investigator=request.user, organization=org_of(request.user))
        log_action(request, "case.create", f"Case {case.case_number} created", case=case)
        return Response(CaseDetailSerializer(case, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CaseDetailAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk):
        case = get_object_or_404(Case.objects.select_related("investigator"), pk=pk)
        require_view(request.user, case)
        return case

    def get(self, request, pk):
        case = self.get_object(request, pk)
        return Response(CaseDetailSerializer(case, context={"request": request}).data)

    def patch(self, request, pk):
        case = self.get_object(request, pk)
        require_edit(request.user, case)
        serializer = CaseWriteSerializer(case, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request, "case.update", "Case metadata updated", case=case)
        return Response(CaseDetailSerializer(case, context={"request": request}).data)

    def delete(self, request, pk):
        case = self.get_object(request, pk)
        require_edit(request.user, case)
        number = case.case_number
        log_action(request, "case.delete", f"Case {number} deleted")
        case.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CaseStatusAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, new_status):
        case = get_object_or_404(Case, pk=pk)
        require_edit(request.user, case)
        if new_status not in Case.Status.values:
            raise ValidationError("Unknown status.")
        case.status = new_status
        case.closed_at = timezone.now() if new_status == Case.Status.CLOSED else None
        case.save()
        log_action(request, "case.status_change", f"Status set to {new_status}", case=case)
        return Response(CaseDetailSerializer(case, context={"request": request}).data)


class CaseReportPdfAPI(APIView):
    """GET /api/cases/<pk>/report/ -- same chain-of-custody PDF as the
    server-rendered view, gated by the plan's feature_pdf_reports flag."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from billing.access import has_feature

        case = get_object_or_404(Case, pk=pk)
        require_view(request.user, case)
        if not has_feature(org_of(request.user), "feature_pdf_reports"):
            raise PlanLimitExceeded(
                "Chain-of-custody PDF reports aren't included on your current plan. Upgrade to unlock it."
            )
        pdf_bytes = build_case_report_pdf(case)
        log_action(request, "case.report_generated", "PDF chain-of-custody report generated", case=case)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{case.case_number}_report.pdf"'
        return response
