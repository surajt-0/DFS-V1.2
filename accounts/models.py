from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        EXAMINER = "examiner", "Forensic Examiner"
        VIEWER = "viewer", "Read-only Reviewer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EXAMINER)
    organization = models.CharField(max_length=150, blank=True, default="Agamya Cyber Tech")
    badge_id = models.CharField(max_length=64, blank=True, help_text="Examiner / badge / employee ID")
    created_at = models.DateTimeField(auto_now_add=True)

    # Tenancy: the billing/subscription organization this user belongs to.
    # `organization` (above) stays as a free-text display label; `org` is the
    # real multi-tenant FK used for data isolation and plan/case limits.
    org = models.ForeignKey(
        "billing.Organization", null=True, blank=True, on_delete=models.SET_NULL, related_name="members"
    )
    is_org_owner = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.user.is_superuser or self.is_org_owner

    @property
    def is_viewer_role(self):
        return self.role == self.Role.VIEWER and not self.is_org_owner and not self.user.is_superuser
