from django.core.management.base import BaseCommand

from billing.models import Plan


# Plans are tiered purely by case volume (no seats/teams). Free is strictly
# view-only -- see Plan.is_read_only / billing.access.is_org_read_only.
PLAN_DEFS = [
    dict(
        key=Plan.Key.FREE, name="Free", tagline="View-only access to a small case load.",
        monthly_price_inr=0, yearly_price_inr=0,
        max_cases=3, yearly_case_bonus=0, max_evidence_per_case=5,
        feature_csv_export=False, feature_xlsx_export=False, feature_json_export=False,
        feature_pdf_reports=False, feature_audit_log=False, feature_local_scan=False,
        feature_data_recovery=False, feature_dns_details=False,
        feature_priority_support=False, feature_custom_branding=False, feature_sso=False,
        sort_order=0,
    ),
    dict(
        key=Plan.Key.PRO, name="Pro", tagline="For active examiners running multiple cases.",
        monthly_price_inr=2499, yearly_price_inr=24990,
        # Yearly subscribers get +10 bonus cases (25 -> 35) for committing annually.
        max_cases=25, yearly_case_bonus=10, max_evidence_per_case=50,
        feature_csv_export=True, feature_xlsx_export=True, feature_json_export=True,
        feature_pdf_reports=True, feature_audit_log=True, feature_local_scan=True,
        feature_data_recovery=True, feature_dns_details=True,
        feature_priority_support=False, feature_custom_branding=False, feature_sso=False,
        sort_order=1,
    ),
    dict(
        key=Plan.Key.ENTERPRISE, name="Enterprise", tagline="Unlimited cases, priority support, custom branding.",
        monthly_price_inr=9999, yearly_price_inr=99990,
        # max_cases=0 already means unlimited, so the bonus is moot here.
        max_cases=0, yearly_case_bonus=0, max_evidence_per_case=0,
        feature_csv_export=True, feature_xlsx_export=True, feature_json_export=True,
        feature_pdf_reports=True, feature_audit_log=True, feature_local_scan=True,
        feature_data_recovery=True, feature_dns_details=True,
        feature_priority_support=True, feature_custom_branding=True, feature_sso=True,
        sort_order=2,
    ),
]


class Command(BaseCommand):
    help = "Create/update the default Free, Pro, and Enterprise plans."

    def handle(self, *args, **options):
        for defaults in PLAN_DEFS:
            key = defaults.pop("key")
            plan, created = Plan.objects.update_or_create(key=key, defaults=defaults)
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{verb} plan: {plan.name}"))
