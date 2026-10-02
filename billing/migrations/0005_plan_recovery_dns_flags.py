from django.db import migrations, models


def enable_for_paid_plans(apps, schema_editor):
    """Existing installs already have Pro/Enterprise rows (and desktop
    installs never re-run seed_plans), so switch the new features on for the
    paid tiers here. Free stays off; admins can still change any of it from
    /admin/ or the Manage Plans screen."""
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(key__in=["pro", "enterprise"]).update(
        feature_data_recovery=True, feature_dns_details=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_plan_yearly_case_bonus_alter_plan_max_cases"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="feature_data_recovery",
            field=models.BooleanField(default=False, verbose_name="Deleted-data & browser system-data recovery"),
        ),
        migrations.AddField(
            model_name="plan",
            name="feature_dns_details",
            field=models.BooleanField(default=False, verbose_name="DNS details"),
        ),
        migrations.RunPython(enable_for_paid_plans, migrations.RunPython.noop),
    ]
