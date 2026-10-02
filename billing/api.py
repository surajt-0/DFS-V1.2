"""JSON API for the React billing SPA. Mirrors billing/views.py exactly (same
model calls, same audit log entries) but returns JSON instead of rendering
templates, so the existing server-rendered billing/ pages keep working
untouched while the React app talks to these endpoints.
"""
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.utils import log_action

from . import razorpay_client
from .access import limit_status, org_of
from .models import Organization, Payment, Plan, Subscription
from .serializers import (
    OrganizationSerializer, PaymentSerializer, PlanAdminSerializer,
    PlanSerializer, SubscriptionSerializer,
)

CYCLE_DAYS = {"monthly": 30, "yearly": 365}


def _org_or_403(user):
    org = org_of(user)
    if org is None or org.owner_id != user.id:
        raise PermissionDenied("Only the organization owner can manage billing.")
    return org


def _require_platform_admin(user):
    if not user.is_superuser:
        raise PermissionDenied("Only platform administrators can change subscription plans.")


def _activate_subscription(org, plan, cycle):
    now = timezone.now()
    period_end = now + timezone.timedelta(days=CYCLE_DAYS[cycle])
    sub, _ = Subscription.objects.update_or_create(
        organization=org,
        defaults=dict(
            plan=plan, billing_cycle=cycle, status=Subscription.Status.ACTIVE,
            current_period_start=now, current_period_end=period_end, cancel_at_period_end=False,
        ),
    )
    org.plan = plan
    org.subscription_status = Organization.Status.ACTIVE
    org.save(update_fields=["plan", "subscription_status"])
    return sub


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class PlanListAPI(APIView):
    """GET /api/billing/plans/ -- public pricing-page data. Superusers get
    every plan (including unpublished drafts); everyone else only sees
    is_public=True plans, same as the Django pricing view."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = Plan.objects.order_by("sort_order", "monthly_price_inr")
        if not (request.user.is_authenticated and request.user.is_superuser):
            qs = qs.filter(is_public=True)
        return Response(PlanSerializer(qs, many=True).data)


class PlanAdminListAPI(APIView):
    """GET /api/billing/admin/plans/ -- every plan, full admin fields."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _require_platform_admin(request.user)
        qs = Plan.objects.order_by("sort_order", "monthly_price_inr")
        return Response(PlanAdminSerializer(qs, many=True).data)


class PlanAdminDetailAPI(APIView):
    """PATCH /api/billing/admin/plans/<id>/ -- the editable surface behind
    'admin can set amount / cases / file access per plan'. Only superusers
    may call this; everything else is 403."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, plan_id):
        _require_platform_admin(request.user)
        plan = get_object_or_404(Plan, pk=plan_id)
        before = dict(
            monthly=plan.monthly_price_inr, yearly=plan.yearly_price_inr,
            cases=plan.max_cases, csv=plan.feature_csv_export,
            xlsx=plan.feature_xlsx_export, json=plan.feature_json_export,
        )
        serializer = PlanAdminSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        plan.refresh_from_db()
        log_action(
            request, "billing.plan_updated",
            f"{plan.name}: cases {before['cases']}->{plan.max_cases}, "
            f"price {before['monthly']}->{plan.monthly_price_inr}/mo, "
            f"csv {before['csv']}->{plan.feature_csv_export}, "
            f"xlsx {before['xlsx']}->{plan.feature_xlsx_export}, "
            f"json {before['json']}->{plan.feature_json_export}"
        )
        return Response(PlanAdminSerializer(plan).data)


# ---------------------------------------------------------------------------
# Current user / org
# ---------------------------------------------------------------------------

class MeAPI(APIView):
    """GET /api/billing/me/ -- who's logged in + their org/role, so the
    React app knows whether to show the admin plan editor, the org-owner
    billing controls, or just the plain pricing page."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        # First call the SPA makes on load -- guarantees the csrftoken
        # cookie is set before any POST/PATCH needs to echo it back.
        if not request.user.is_authenticated:
            return Response({"authenticated": False})
        org = org_of(request.user)
        profile = getattr(request.user, "profile", None)
        return Response({
            "authenticated": True,
            "username": request.user.username,
            "email": request.user.email,
            "is_superuser": request.user.is_superuser,
            "is_org_owner": bool(org and org.owner_id == request.user.id),
            "role": getattr(profile, "role", None),
            "is_admin": bool(profile and profile.is_admin_role),
            "is_viewer": bool(profile and profile.is_viewer_role),
            "organization": OrganizationSerializer(org).data if org else None,
        })


class MySubscriptionAPI(APIView):
    """GET /api/billing/my/ -- billing dashboard data for the logged-in
    user's organization."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = org_of(request.user)
        if org is None:
            return Response({"detail": "Your account isn't attached to an organization."}, status=400)
        payments = org.payments.order_by("-created_at")[:25]
        return Response({
            "organization": OrganizationSerializer(org).data,
            "case_usage": limit_status(org, "cases"),
            "is_owner": org.owner_id == request.user.id,
            "payments": PaymentSerializer(payments, many=True).data,
        })


class PaymentListAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = org_of(request.user)
        if org is None:
            return Response([])
        payments = org.payments.order_by("-created_at")
        return Response(PaymentSerializer(payments, many=True).data)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

class CheckoutCreateAPI(APIView):
    """POST /api/billing/checkout/<plan_key>/<cycle>/ -- creates a Razorpay
    order (or a demo one if keys aren't configured) for the org owner to pay."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, plan_key, cycle):
        org = _org_or_403(request.user)
        plan = get_object_or_404(Plan, key=plan_key, is_public=True)
        if cycle not in CYCLE_DAYS:
            raise ValidationError("Invalid billing cycle.")
        if plan.is_free:
            return Response({"free": True, "detail": "The Free plan doesn't require checkout."})

        amount = plan.price_for(cycle)
        order = razorpay_client.create_order(
            amount_rupees=amount, currency="INR",
            receipt=f"{org.slug}-{plan.key}-{cycle}",
            notes={"organization": org.name, "plan": plan.key, "cycle": cycle},
        )
        payment = Payment.objects.create(
            organization=org, plan=plan, billing_cycle=cycle,
            razorpay_order_id=order["id"], amount_inr=amount,
            status=Payment.Status.CREATED, is_demo=order.get("demo", False),
            created_by=request.user,
        )
        return Response({
            "payment_id": payment.id,
            "plan": PlanSerializer(plan).data,
            "cycle": cycle,
            "order": order,
            "amount_paise": order["amount"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "demo_mode": order.get("demo", False),
            "prefill_email": request.user.email,
            "prefill_name": request.user.get_full_name() or request.user.username,
        })


class CheckoutVerifyAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, payment_id):
        org = org_of(request.user)
        payment = get_object_or_404(Payment, pk=payment_id, organization=org)
        razorpay_payment_id = request.data.get("razorpay_payment_id", "")
        razorpay_signature = request.data.get("razorpay_signature", "")

        ok = razorpay_client.verify_payment_signature(
            payment.razorpay_order_id, razorpay_payment_id, razorpay_signature
        )
        if not ok:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            log_action(request, "billing.payment_failed", f"Payment verification failed for {payment.invoice_number}")
            return Response({"ok": False, "message": "Payment verification failed."}, status=400)

        with transaction.atomic():
            payment.razorpay_payment_id = razorpay_payment_id or f"pay_DEMO{payment.pk}"
            payment.razorpay_signature = razorpay_signature
            payment.status = Payment.Status.PAID
            payment.save(update_fields=["razorpay_payment_id", "razorpay_signature", "status"])
            _activate_subscription(payment.organization, payment.plan, payment.billing_cycle)

        log_action(
            request, "billing.subscription_activated",
            f"Upgraded to {payment.plan.name} ({payment.billing_cycle}), invoice {payment.invoice_number}"
        )
        return Response({"ok": True, "plan": PlanSerializer(payment.plan).data})


# ---------------------------------------------------------------------------
# Modify / cancel
# ---------------------------------------------------------------------------

class SubscriptionModifyAPI(APIView):
    """POST /api/billing/my/modify/ {plan_key, cycle} -- switching to Free
    applies immediately; switching to/within a paid plan hands back a flag
    telling the SPA to go through checkout."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        org = _org_or_403(request.user)
        subscription = getattr(org, "subscription", None)
        plan_key = request.data.get("plan_key", "")
        cycle = request.data.get("cycle", "monthly")
        new_plan = get_object_or_404(Plan, key=plan_key, is_public=True)

        if cycle not in CYCLE_DAYS:
            raise ValidationError("Invalid billing cycle.")

        no_change = (
            new_plan.id == org.plan_id
            and (subscription is None or subscription.billing_cycle == cycle or new_plan.is_free)
        )
        if no_change:
            return Response({"ok": True, "no_change": True, "detail": "That's already your current plan."})

        if new_plan.is_free:
            if subscription:
                subscription.status = Subscription.Status.CANCELED
                subscription.cancel_at_period_end = True
                subscription.save(update_fields=["status", "cancel_at_period_end"])
            org.plan = new_plan
            org.subscription_status = Organization.Status.ACTIVE
            org.save(update_fields=["plan", "subscription_status"])
            log_action(request, "billing.subscription_modified", f"Switched to {new_plan.name} (Free)")
            return Response({"ok": True, "organization": OrganizationSerializer(org).data})

        return Response({"ok": True, "requires_checkout": True, "plan_key": new_plan.key, "cycle": cycle})


class SubscriptionCancelAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        org = _org_or_403(request.user)
        sub = getattr(org, "subscription", None)
        free = Plan.objects.filter(key=Plan.Key.FREE).first()
        if sub:
            sub.status = Subscription.Status.CANCELED
            sub.cancel_at_period_end = True
            sub.save(update_fields=["status", "cancel_at_period_end"])
        if free:
            org.plan = free
        org.subscription_status = Organization.Status.CANCELED
        org.save(update_fields=["plan", "subscription_status"])
        log_action(request, "billing.subscription_canceled", f"Subscription canceled, moved to {org.plan.name}")
        return Response({"ok": True, "organization": OrganizationSerializer(org).data})


class DowngradeFreeAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        org = _org_or_403(request.user)
        free = Plan.objects.get(key=Plan.Key.FREE)
        org.plan = free
        org.subscription_status = Organization.Status.ACTIVE
        org.save(update_fields=["plan", "subscription_status"])
        return Response({"ok": True, "organization": OrganizationSerializer(org).data})
