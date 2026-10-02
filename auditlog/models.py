from django.conf import settings
from django.db import models


class AuditLogEntry(models.Model):
    """Every meaningful action in the suite -- logins, uploads, parses,
    exports, report generation, case lifecycle changes -- lands here as an
    immutable, timestamped row. This IS the chain-of-custody trail."""

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_entries"
    )
    username_snapshot = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    detail = models.TextField(blank=True)
    case = models.ForeignKey(
        "cases.Case", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    path = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit log entry"
        verbose_name_plural = "Audit log entries"

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.username_snapshot}: {self.action}"
