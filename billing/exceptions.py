"""Plan/billing-driven restrictions are surfaced as HTTP 402 Payment
Required, distinct from HTTP 403 Forbidden which is reserved for
role-based authorization failures (e.g. a viewer trying to edit a case).

Rule of thumb used across cases/api.py, evidence/api.py, and billing/api.py:
  - "Your ROLE doesn't allow this"  -> PermissionDenied (403)
  - "Your PLAN doesn't allow this"  -> PlanLimitExceeded (402)
    (case/evidence quota reached, Free read-only tier, a gated feature
    like PDF reports or an export format not on the current plan)
"""
from rest_framework import status
from rest_framework.exceptions import APIException


class PlanLimitExceeded(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Your current plan doesn't allow this. Upgrade to continue."
    default_code = "plan_limit_exceeded"
