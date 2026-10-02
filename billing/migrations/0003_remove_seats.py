from django.db import migrations


class Migration(migrations.Migration):
    """Removes the seats/teams concept: Plan.max_users and
    Organization.seat_count (a Python @property, not a DB column, so no
    schema change needed for that one)."""

    dependencies = [
        ('billing', '0002_backfill_legacy_org'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plan',
            name='max_users',
        ),
    ]
