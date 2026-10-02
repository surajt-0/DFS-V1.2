from rest_framework import serializers

from .models import Organization, Payment, Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    """Public-facing plan representation used on the pricing page. Every
    field here is safe to show to a logged-out visitor."""

    features = serializers.SerializerMethodField()
    file_access = serializers.SerializerMethodField()
    max_cases_yearly = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id", "key", "name", "tagline",
            "monthly_price_inr", "yearly_price_inr",
            "max_cases", "yearly_case_bonus", "max_cases_yearly", "max_evidence_per_case",
            "feature_csv_export", "feature_xlsx_export", "feature_json_export",
            "feature_pdf_reports", "feature_audit_log", "feature_local_scan",
            "feature_data_recovery", "feature_dns_details",
            "feature_priority_support", "feature_custom_branding", "feature_sso",
            "is_public", "sort_order", "is_free", "is_read_only",
            "features", "file_access",
        ]
        read_only_fields = fields

    def get_features(self, obj):
        return obj.feature_list()

    def get_max_cases_yearly(self, obj):
        """The effective case limit a yearly subscriber gets on this plan
        (base max_cases + yearly_case_bonus, still 0 for unlimited) --
        exposed so the pricing page can advertise 'X cases/mo, or Y with
        annual billing' without duplicating the arithmetic client-side."""
        return obj.max_cases_for("yearly")

    def get_file_access(self, obj):
        """Which file/export formats this plan's members can access --
        surfaced separately so the React pricing cards and the admin panel
        can render a dedicated 'File access' section."""
        return {
            "csv_export": obj.feature_csv_export,
            "xlsx_export": obj.feature_xlsx_export,
            "json_export": obj.feature_json_export,
            "pdf_reports": obj.feature_pdf_reports,
            "audit_log": obj.feature_audit_log,
            "local_scan": obj.feature_local_scan,
            "data_recovery": obj.feature_data_recovery,
            "dns_details": obj.feature_dns_details,
        }


class PlanAdminSerializer(serializers.ModelSerializer):
    """Full read/write representation for platform admins: pricing (monthly
    + yearly), the case-volume limit the subscription is built on, and every
    per-file-type access flag."""

    class Meta:
        model = Plan
        fields = [
            "id", "key", "name", "tagline",
            "monthly_price_inr", "yearly_price_inr",
            "max_cases", "yearly_case_bonus", "max_evidence_per_case",
            "feature_csv_export", "feature_xlsx_export", "feature_json_export",
            "feature_pdf_reports", "feature_audit_log", "feature_local_scan",
            "feature_data_recovery", "feature_dns_details",
            "feature_priority_support", "feature_custom_branding", "feature_sso",
            "is_public", "sort_order",
        ]
        read_only_fields = ["id", "key"]

    def validate_monthly_price_inr(self, value):
        if value < 0:
            raise serializers.ValidationError("Price can't be negative.")
        return value

    def validate_yearly_price_inr(self, value):
        if value < 0:
            raise serializers.ValidationError("Price can't be negative.")
        return value

    def validate_max_cases(self, value):
        if value < 0:
            raise serializers.ValidationError("Case limit can't be negative.")
        return value

    def validate_yearly_case_bonus(self, value):
        if value < 0:
            raise serializers.ValidationError("Yearly bonus can't be negative.")
        return value

    def validate_max_evidence_per_case(self, value):
        if value < 0:
            raise serializers.ValidationError("Evidence-per-case limit can't be negative.")
        return value


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "plan", "billing_cycle", "status",
            "current_period_start", "current_period_end",
            "cancel_at_period_end", "renews_soon",
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    subscription = SubscriptionSerializer(read_only=True)
    case_count = serializers.ReadOnlyField()
    is_on_paid_plan = serializers.ReadOnlyField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "slug", "plan", "subscription_status",
            "subscription", "case_count", "is_on_paid_plan", "created_at",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "invoice_number", "plan_name", "billing_cycle",
            "amount_inr", "currency", "status", "is_demo", "created_at",
        ]
