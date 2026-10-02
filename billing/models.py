import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class Plan(models.Model):
    """A sellable tier. Free/Pro/Enterprise ship out of the box (see
    `billing/management/commands/seed_plans.py`) but more can be added from
    the admin without touching code -- limits and feature flags are all
    data-driven."""

    class Key(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    key = models.CharField(max_length=20, choices=Key.choices, unique=True)
    name = models.CharField(max_length=60)
    tagline = models.CharField(max_length=160, blank=True)

    monthly_price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    yearly_price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Razorpay Plan IDs, only needed if you wire up Razorpay Subscriptions
    # (recurring auto-debit) instead of the one-off Order-per-renewal flow
    # this suite uses by default.
    razorpay_plan_id_monthly = models.CharField(max_length=64, blank=True)
    razorpay_plan_id_yearly = models.CharField(max_length=64, blank=True)

    # ---- Limits. 0 means unlimited. ----
    # Plans are tiered purely by case volume -- there is no seat/team concept
    # in this suite; every organization is single-owner.
    max_cases = models.PositiveIntegerField(default=3, help_text="Active cases per organization on MONTHLY billing. 0 = unlimited.")
    max_evidence_per_case = models.PositiveIntegerField(default=5, help_text="Evidence files per case. 0 = unlimited.")
    yearly_case_bonus = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Extra cases granted on top of max_cases when the organization is billed "
            "YEARLY for this plan (reward for committing annually). Ignored when "
            "max_cases is 0 (unlimited). E.g. max_cases=25, yearly_case_bonus=10 -> "
            "yearly subscribers get 35 cases."
        ),
    )

    # ---- Feature flags ----
    feature_csv_export = models.BooleanField(default=True, verbose_name="CSV export")
    feature_xlsx_export = models.BooleanField(default=False, verbose_name="XLSX export")
    feature_json_export = models.BooleanField(default=False, verbose_name="JSON export")
    feature_pdf_reports = models.BooleanField(default=False, verbose_name="Chain-of-custody PDF reports")
    feature_audit_log = models.BooleanField(default=False, verbose_name="Full session/audit log access")
    feature_local_scan = models.BooleanField(default=False, verbose_name="Local workstation scan")
    feature_data_recovery = models.BooleanField(
        default=False, verbose_name="Deleted-data & browser system-data recovery")
    feature_dns_details = models.BooleanField(default=False, verbose_name="DNS details")
    feature_priority_support = models.BooleanField(default=False, verbose_name="Priority support")
    feature_custom_branding = models.BooleanField(default=False, verbose_name="Custom branding")
    feature_sso = models.BooleanField(default=False, verbose_name="SSO / SAML (enterprise)")

    is_public = models.BooleanField(default=True, help_text="Shown on the pricing page.")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "monthly_price_inr"]

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return self.monthly_price_inr == 0 and self.yearly_price_inr == 0

    @property
    def is_read_only(self):
        """Free-tier organizations get strict view-only access: no case or
        evidence creation/edits, regardless of the member's role."""
        return self.key == self.Key.FREE

    def price_for(self, cycle):
        return self.yearly_price_inr if cycle == "yearly" else self.monthly_price_inr

    def max_cases_for(self, cycle):
        """Effective case limit for a given billing cycle ('monthly' or
        'yearly'). Yearly subscribers get `yearly_case_bonus` extra cases on
        top of the base `max_cases`, as an incentive for committing annually.
        0 (unlimited) always stays unlimited regardless of cycle."""
        if self.max_cases == 0:
            return 0
        if cycle == "yearly":
            return self.max_cases + self.yearly_case_bonus
        return self.max_cases

    def feature_list(self):
        """Human labels for every feature flag currently on, for pricing cards."""
        labels = {
            "feature_csv_export": "CSV export",
            "feature_xlsx_export": "XLSX export",
            "feature_json_export": "JSON export",
            "feature_pdf_reports": "Chain-of-custody PDF reports",
            "feature_audit_log": "Full audit log access",
            "feature_local_scan": "Local workstation scan",
            "feature_data_recovery": "Deleted-data & browser system-data recovery",
            "feature_dns_details": "DNS details",
            "feature_priority_support": "Priority support",
            "feature_custom_branding": "Custom branding",
            "feature_sso": "SSO / SAML",
        }
        return [label for field, label in labels.items() if getattr(self, field)]


class Organization(models.Model):
    """The tenant. Every user belongs to exactly one Organization (via
    accounts.Profile.org); every Case belongs to exactly one Organization.
    This is the isolation boundary."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIALING = "trialing", "Trialing"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_organizations"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="organizations")
    subscription_status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    razorpay_customer_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:140] or "org"
            self.slug = f"{base}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def case_count(self):
        return self.cases.count()

    @property
    def is_on_paid_plan(self):
        return not self.plan.is_free and self.subscription_status in (
            Organization.Status.ACTIVE, Organization.Status.TRIALING
        )


class Subscription(models.Model):
    """The live billing record for an Organization's paid plan. A free-plan
    org has no Subscription row -- absence of a row means 'on Free'."""

    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    billing_cycle = models.CharField(max_length=10, choices=Cycle.choices, default=Cycle.MONTHLY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    razorpay_subscription_id = models.CharField(max_length=64, blank=True)

    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization.name} -> {self.plan.name} ({self.billing_cycle})"

    @property
    def renews_soon(self):
        if not self.current_period_end:
            return False
        return 0 <= (self.current_period_end - timezone.now()).days <= 7


class Payment(models.Model):
    """One row per Razorpay order/payment attempt. This is also the
    customer-facing invoice list."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    billing_cycle = models.CharField(max_length=10, choices=Subscription.Cycle.choices, default=Subscription.Cycle.MONTHLY)

    invoice_number = models.CharField(max_length=32, unique=True, editable=False, blank=True)
    razorpay_order_id = models.CharField(max_length=64, blank=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    razorpay_signature = models.CharField(max_length=256, blank=True)

    amount_inr = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="INR")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    is_demo = models.BooleanField(
        default=False,
        help_text="True when created without a live Razorpay key configured (RAZORPAY_KEY_ID/SECRET).",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="billing_payments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} ({self.get_status_display()})"
