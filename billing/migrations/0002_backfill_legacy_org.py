from django.db import migrations


def backfill_legacy_organization(apps, schema_editor):
    Plan = apps.get_model('billing', 'Plan')
    Organization = apps.get_model('billing', 'Organization')
    Profile = apps.get_model('accounts', 'Profile')
    Case = apps.get_model('cases', 'Case')

    orphan_profiles = Profile.objects.filter(org__isnull=True)
    if not orphan_profiles.exists():
        return

    free_plan, _ = Plan.objects.get_or_create(
        key='free',
        defaults=dict(name='Free', tagline='Get started with a single case.', max_users=1, max_cases=3, max_evidence_per_case=5, feature_csv_export=True),
    )

    # One shared "Legacy" organization for whatever existed before
    # multi-tenancy was introduced. Deployments with real customer data
    # should split this manually afterward via the admin (Organization ->
    # add new orgs, then reassign Profile.org / Case.organization).
    owner_profile = orphan_profiles.order_by('user_id').first()
    org, _ = Organization.objects.get_or_create(
        slug='legacy-org',
        defaults=dict(name='Legacy Organization (pre-billing data)', owner_id=owner_profile.user_id, plan=free_plan),
    )

    orphan_profiles.update(org=org)
    Case.objects.filter(organization__isnull=True).update(organization=org)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
        ('accounts', '0002_profile_org'),
        ('cases', '0002_case_organization'),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_organization, noop_reverse),
    ]
