from django.contrib import admin

from .models import Organization, Payment, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "monthly_price_inr", "yearly_price_inr", "max_cases", "max_evidence_per_case", "is_public")
    list_editable = ("is_public",)
    fieldsets = (
        (None, {"fields": ("key", "name", "tagline", "is_public", "sort_order")}),
        ("Pricing (INR)", {"fields": ("monthly_price_inr", "yearly_price_inr", "razorpay_plan_id_monthly", "razorpay_plan_id_yearly")}),
        ("Limits (0 = unlimited)", {"fields": ("max_cases", "max_evidence_per_case")}),
        ("Features", {"fields": (
            "feature_csv_export", "feature_xlsx_export", "feature_json_export",
            "feature_pdf_reports", "feature_audit_log", "feature_local_scan",
            "feature_data_recovery", "feature_dns_details",
            "feature_priority_support", "feature_custom_branding", "feature_sso",
        )}),
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "plan", "subscription_status", "case_count", "created_at")
    list_filter = ("subscription_status", "plan")
    search_fields = ("name", "slug", "owner__username")
    readonly_fields = ("slug", "created_at")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "billing_cycle", "status", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "billing_cycle", "plan")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "organization", "plan", "amount_inr", "status", "is_demo", "created_at")
    list_filter = ("status", "is_demo", "plan")
    search_fields = ("invoice_number", "razorpay_order_id", "razorpay_payment_id", "organization__name")
    readonly_fields = ("invoice_number", "created_at")
