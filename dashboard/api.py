from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.models import AuditLogEntry
from billing.access import limit_status, org_of
from cases.models import Case
from cases.serializers import CaseListSerializer
from core.permissions import visible_cases_qs
from evidence.models import EvidenceItem


class DashboardStatsAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cases_qs = visible_cases_qs(request.user, Case.objects.all())
        org = org_of(request.user)

        stats = {
            "total_cases": cases_qs.count(),
            "open_cases": cases_qs.filter(status=Case.Status.OPEN).count(),
            "closed_cases": cases_qs.filter(status=Case.Status.CLOSED).count(),
            "total_evidence": EvidenceItem.objects.filter(case__in=cases_qs).count(),
            "parsed_evidence": EvidenceItem.objects.filter(case__in=cases_qs, status=EvidenceItem.Status.PARSED).count(),
        }

        type_breakdown = list(
            EvidenceItem.objects.filter(case__in=cases_qs)
            .values("evidence_type").annotate(n=Count("id")).order_by("-n")
        )

        recent_cases = cases_qs.select_related("investigator").order_by("-updated_at")[:6]

        org_entries = AuditLogEntry.objects.filter(
            Q(user__profile__org=org) | Q(case__organization=org)
        )
        profile = request.user.profile
        if profile.is_admin_role or profile.is_viewer_role:
            recent_activity_qs = org_entries.select_related("user", "case").order_by("-timestamp")[:12]
        else:
            recent_activity_qs = org_entries.filter(user=request.user).select_related("case").order_by("-timestamp")[:12]

        week_ago = timezone.now() - timedelta(days=7)
        activity_filter = {} if (profile.is_admin_role or profile.is_viewer_role) else {"user": request.user}
        activity_last_week = org_entries.filter(timestamp__gte=week_ago, **activity_filter).count()

        from auditlog.serializers import AuditLogEntrySerializer

        return Response({
            "stats": stats,
            "type_breakdown": type_breakdown,
            "recent_cases": CaseListSerializer(recent_cases, many=True).data,
            "recent_activity": AuditLogEntrySerializer(recent_activity_qs, many=True).data,
            "activity_last_week": activity_last_week,
            "case_usage": limit_status(org, "cases"),
        })
