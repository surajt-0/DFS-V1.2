import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('free', 'Free'), ('pro', 'Pro'), ('enterprise', 'Enterprise')], max_length=20, unique=True)),
                ('name', models.CharField(max_length=60)),
                ('tagline', models.CharField(blank=True, max_length=160)),
                ('monthly_price_inr', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('yearly_price_inr', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('razorpay_plan_id_monthly', models.CharField(blank=True, max_length=64)),
                ('razorpay_plan_id_yearly', models.CharField(blank=True, max_length=64)),
                ('max_users', models.PositiveIntegerField(default=1, help_text='Seats per organization. 0 = unlimited.')),
                ('max_cases', models.PositiveIntegerField(default=3, help_text='Active cases per organization. 0 = unlimited.')),
                ('max_evidence_per_case', models.PositiveIntegerField(default=5, help_text='Evidence files per case. 0 = unlimited.')),
                ('feature_csv_export', models.BooleanField(default=True, verbose_name='CSV export')),
                ('feature_xlsx_export', models.BooleanField(default=False, verbose_name='XLSX export')),
                ('feature_json_export', models.BooleanField(default=False, verbose_name='JSON export')),
                ('feature_pdf_reports', models.BooleanField(default=False, verbose_name='Chain-of-custody PDF reports')),
                ('feature_audit_log', models.BooleanField(default=False, verbose_name='Full session/audit log access')),
                ('feature_local_scan', models.BooleanField(default=False, verbose_name='Local workstation scan')),
                ('feature_priority_support', models.BooleanField(default=False, verbose_name='Priority support')),
                ('feature_custom_branding', models.BooleanField(default=False, verbose_name='Custom branding')),
                ('feature_sso', models.BooleanField(default=False, verbose_name='SSO / SAML (enterprise)')),
                ('is_public', models.BooleanField(default=True, help_text='Shown on the pricing page.')),
                ('sort_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ['sort_order', 'monthly_price_inr'],
            },
        ),
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('slug', models.SlugField(editable=False, max_length=170, unique=True)),
                ('subscription_status', models.CharField(choices=[('active', 'Active'), ('trialing', 'Trialing'), ('past_due', 'Past due'), ('canceled', 'Canceled')], default='active', max_length=16)),
                ('razorpay_customer_id', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_organizations', to=settings.AUTH_USER_MODEL)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='organizations', to='billing.plan')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('billing_cycle', models.CharField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly', max_length=10)),
                ('status', models.CharField(choices=[('active', 'Active'), ('past_due', 'Past due'), ('canceled', 'Canceled')], default='active', max_length=16)),
                ('razorpay_subscription_id', models.CharField(blank=True, max_length=64)),
                ('current_period_start', models.DateTimeField(default=django.utils.timezone.now)),
                ('current_period_end', models.DateTimeField(blank=True, null=True)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='billing.organization')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subscriptions', to='billing.plan')),
            ],
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('billing_cycle', models.CharField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly', max_length=10)),
                ('invoice_number', models.CharField(blank=True, editable=False, max_length=32, unique=True)),
                ('razorpay_order_id', models.CharField(blank=True, max_length=64)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=64)),
                ('razorpay_signature', models.CharField(blank=True, max_length=256)),
                ('amount_inr', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='INR', max_length=8)),
                ('status', models.CharField(choices=[('created', 'Created'), ('paid', 'Paid'), ('failed', 'Failed')], default='created', max_length=16)),
                ('is_demo', models.BooleanField(default=False, help_text='True when created without a live Razorpay key configured (RAZORPAY_KEY_ID/SECRET).')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='billing_payments', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='billing.organization')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='billing.plan')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
