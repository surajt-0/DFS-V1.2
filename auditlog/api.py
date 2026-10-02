from django.db.models import Q
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.access import has_feature, org_of

from .models import AuditLogEntry
from .serializers import AuditLogEntrySerializer


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AuditLogListAPI(APIView):
    """GET /api/audit/ -- same tenant + role + plan-feature scoping as the
    server-rendered auditlog/list.html: full org-wide history requires the
    plan's feature_audit_log flag, otherwise each user sees only their own
    actions."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = AuditLogPagination

    def get(self, request):
        org = org_of(request.user)
        profile = request.user.profile

        qs = AuditLogEntry.objects.select_related("user", "case").filter(
            Q(user__profile__org=org) | Q(case__organization=org)
        )

        sees_org_wide = (profile.is_admin_role or profile.is_viewer_role) and has_feature(org, "feature_audit_log")
        if not sees_org_wide:
            qs = qs.filter(user=request.user)

        q = request.GET.get("q", "").strip()
        action = request.GET.get("action", "").strip()
        if q:
            qs = qs.filter(Q(detail__icontains=q) | Q(username_snapshot__icontains=q) | Q(path__icontains=q))
        if action:
            qs = qs.filter(action=action)

        actions = sorted(set(qs.order_by().values_list("action", flat=True).distinct()))

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        data = AuditLogEntrySerializer(page, many=True).data
        response = paginator.get_paginated_response(data)
        response.data["actions"] = actions
        response.data["org_wide"] = sees_org_wide
        response.data["feature_audit_log"] = has_feature(org, "feature_audit_log")
        return response
