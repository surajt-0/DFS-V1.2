from django.conf import settings


def suite_context(request):
    """Global template context: suite branding + a couple of nav badges."""
    ctx = {
        "SUITE_NAME": settings.SUITE_NAME,
        "SUITE_ORG": settings.SUITE_ORG,
        "SUITE_VERSION": settings.SUITE_VERSION,
    }
    if request.user.is_authenticated:
        try:
            from cases.models import Case
            from core.permissions import visible_cases_qs
            ctx["nav_open_cases"] = visible_cases_qs(
                request.user, Case.objects.filter(status=Case.Status.OPEN)
            ).count()
        except Exception:
            ctx["nav_open_cases"] = 0
        try:
            from billing.access import org_of, effective_plan, is_org_read_only
            org = org_of(request.user)
            ctx["nav_org"] = org
            ctx["nav_plan"] = effective_plan(org)
            ctx["nav_read_only"] = is_org_read_only(org)
        except Exception:
            ctx["nav_org"] = None
            ctx["nav_plan"] = None
            ctx["nav_read_only"] = False
    return ctx
