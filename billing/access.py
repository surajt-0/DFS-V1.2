"""Central place for 'is this org allowed to do X' logic. Consumed by the
DRF API layer (cases/api.py, evidence/api.py, billing/api.py) which is the
only client-facing surface -- the React SPA is the client, this module is
where its plan/billing rules are enforced server-side.
"""
from .models import Plan


def free_plan():
    plan, _ = Plan.objects.get_or_create(
        key=Plan.Key.FREE,
        defaults=dict(
            name="Free", tagline="View-only access to a small case load.",
            monthly_price_inr=0, yearly_price_inr=0,
            max_cases=3, max_evidence_per_case=5,
            feature_csv_export=False, sort_order=0,
        ),
    )
    return plan


def org_of(user):
    if not getattr(user, "is_authenticated", False):
        return None
    profile = getattr(user, "profile", None)
    return getattr(profile, "org", None) if profile else None


def effective_plan(org):
    if org is None:
        return free_plan()
    return org.plan or free_plan()


def has_feature(org, feature_field: str) -> bool:
    plan = effective_plan(org)
    return bool(getattr(plan, feature_field, False))


def is_org_read_only(org) -> bool:
    """True for organizations on the Free tier: they may only view existing
    data (cases, evidence, artifact tables) -- no creating, editing,
    deleting, or uploading, regardless of the member's role."""
    return effective_plan(org).is_read_only


def billing_cycle_of(org) -> str:
    """The org's active billing cycle ('monthly' or 'yearly'). Orgs without
    a live Subscription row (i.e. on Free) are treated as monthly -- it's
    moot there since Free's bonus is always 0."""
    sub = getattr(org, "subscription", None) if org else None
    return sub.billing_cycle if sub else "monthly"


def limit_status(org, kind: str):
    """kind == 'cases' (evidence needs a case kwarg, handled by caller via
    evidence_limit_status). Returns dict with used, limit (0 = unlimited),
    remaining, allowed(bool: room for one more). Yearly-billed orgs get their
    plan's yearly_case_bonus added on top of the base case limit."""
    plan = effective_plan(org)
    if kind == "cases":
        cycle = billing_cycle_of(org)
        limit = plan.max_cases_for(cycle)
        used = org.case_count if org else 0
    else:
        raise ValueError(kind)
    unlimited = limit == 0
    remaining = None if unlimited else max(limit - used, 0)
    return {
        "used": used, "limit": limit, "unlimited": unlimited,
        "remaining": remaining, "allowed": unlimited or used < limit,
        "billing_cycle": billing_cycle_of(org) if org else "monthly",
    }


def evidence_limit_status(org, case):
    plan = effective_plan(org)
    limit = plan.max_evidence_per_case
    used = case.evidence_items.count()
    unlimited = limit == 0
    remaining = None if unlimited else max(limit - used, 0)
    return {
        "used": used, "limit": limit, "unlimited": unlimited,
        "remaining": remaining, "allowed": unlimited or used < limit,
    }
