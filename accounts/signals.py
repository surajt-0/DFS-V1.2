from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    """Every user gets a Profile automatically -- admin-created accounts via
    `createsuperuser` included -- so role checks never hit a DoesNotExist."""
    if created:
        profile, _ = Profile.objects.get_or_create(user=instance, defaults={
            "role": Profile.Role.ADMIN if instance.is_superuser else Profile.Role.EXAMINER
        })
        # `createsuperuser` accounts bypass the signup form (and therefore
        # SignUpForm's Organization-creation step), so give them their own
        # organization here on the top plan -- otherwise every org-scoped
        # view would show them nothing.
        if instance.is_superuser and not profile.org_id:
            from billing.access import free_plan
            from billing.models import Organization, Plan
            plan = Plan.objects.filter(key=Plan.Key.ENTERPRISE).first() or free_plan()
            org = Organization.objects.create(name=f"{instance.username} (platform admin)", owner=instance, plan=plan)
            profile.org = org
            profile.is_org_owner = True
            profile.save(update_fields=["org", "is_org_owner"])
