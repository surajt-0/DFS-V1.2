import uuid

from django.conf import settings
from django.db import models


class Case(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        ARCHIVED = "archived", "Archived"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    case_number = models.CharField(max_length=32, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    investigator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cases"
    )
    organization = models.ForeignKey(
        "billing.Organization", on_delete=models.CASCADE, related_name="cases", null=True, blank=True
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    subject_name = models.CharField("Subject / custodian", max_length=200, blank=True)
    tags = models.CharField(max_length=300, blank=True, help_text="Comma-separated tags")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.case_number:
            self.case_number = f"DFS-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.case_number} - {self.name}"

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def evidence_count(self):
        return self.evidence_items.count()

    @property
    def parsed_evidence_count(self):
        return self.evidence_items.filter(status="parsed").count()
