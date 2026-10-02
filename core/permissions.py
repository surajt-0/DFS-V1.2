"""Centralised, tiny permission rules for the suite's three roles:
  - admin    : sees and manages every case *within their own organization*
  - examiner : full control over cases they are assigned as investigator
  - viewer   : read-only access to every case in their organization

All access is additionally scoped to the caller's Organization (tenant) --
role does not grant cross-organization visibility.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied


def _same_org(user, case) -> bool:
    org_id = getattr(user.profile, "org_id", None)
    return org_id is not None and case.organization_id == org_id


def can_view_case(user, case) -> bool:
    if not user.is_authenticated:
        return False
    if not _same_org(user, case):
        return False
    profile = user.profile
    if profile.is_admin_role or profile.is_viewer_role:
        return True
    return case.investigator_id == user.id


def can_edit_case(user, case) -> bool:
    if not user.is_authenticated:
        return False
    if not _same_org(user, case):
        return False
    from billing.access import is_org_read_only
    if is_org_read_only(case.organization):
        return False
    profile = user.profile
    if profile.is_viewer_role:
        return False
    if profile.is_admin_role:
        return True
    return case.investigator_id == user.id


def can_upload_evidence(user, case) -> bool:
    """Who may add evidence files (manual upload AND the automatic local
    scan) to a case. Deliberately separate from can_edit_case: on a paid
    plan (Pro/Enterprise) *every* role in the organization -- admin,
    examiner, and read-only reviewer alike -- can upload evidence to any
    case they can see, while editing/deleting the case itself, changing
    its status, or removing evidence stay restricted to can_edit_case.

    Set DFS_EVIDENCE_UPLOAD_ALL_ROLES=False to fall back to the stricter
    "same as editing" rule (viewers can never upload) on deployments that
    want a truly read-only reviewer role. The Free plan is read-only for
    every role regardless of this setting.
    """
    if not user.is_authenticated:
        return False
    if not can_view_case(user, case):
        return False
    from billing.access import is_org_read_only
    if is_org_read_only(case.organization):
        return False
    if getattr(settings, "EVIDENCE_UPLOAD_ALL_ROLES", True):
        return True
    return can_edit_case(user, case)


def require_view(user, case):
    if not can_view_case(user, case):
        raise PermissionDenied("You do not have access to this case.")


def require_edit(user, case):
    if not can_edit_case(user, case):
        raise PermissionDenied("You do not have permission to modify this case.")


def require_upload_evidence(user, case):
    if not can_upload_evidence(user, case):
        raise PermissionDenied("You do not have permission to upload evidence to this case.")


def visible_cases_qs(user, base_qs):
    profile = user.profile
    if not profile.org_id:
        return base_qs.none()
    qs = base_qs.filter(organization_id=profile.org_id)
    if profile.is_admin_role or profile.is_viewer_role:
        return qs
    return qs.filter(investigator=user)
