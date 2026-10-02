"""Storage for the three recovery modules.

RecoveredRecord  rows carved out of deleted / unallocated space, freelist
                 pages and WAL files of browser SQLite databases
StateItem        browser "system data": sessions & closed tabs, bookmarks
                 (incl. backup-only ones), extensions, preferences, network state
DnsEntry         DNS details: hosts-file entries, resolver config, cached
                 records, active lookups
RecoveryRun      one execution of the carver (stats + warnings, for the
                 chain-of-custody trail and the report)

None of these models has a field able to hold a password or cookie value.
"""
from django.conf import settings
from django.db import models

from cases.models import Case
from evidence.models import EvidenceItem


class RecoveryRun(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "Completed"
        PARTIAL = "partial", "Completed with warnings"
        FAILED = "failed", "Failed"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="recovery_runs")
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="recovery_runs")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OK)
    records_found = models.IntegerField(default=0)
    stats = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    wal_used = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class RecoveredRecord(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="recovered_records")
    run = models.ForeignKey(RecoveryRun, on_delete=models.CASCADE, related_name="records")
    kind = models.CharField(max_length=16, db_index=True)        # history | download | cookie | login
    browser = models.CharField(max_length=16)                     # chromium | firefox
    table_name = models.CharField(max_length=32)
    source = models.CharField(max_length=16, db_index=True)       # freelist_page | freeblock | wal | wal_stale
    confidence = models.CharField(max_length=8, db_index=True)    # high | medium | low
    status = models.CharField(max_length=16, db_index=True)       # deleted | older_version | wal_only
    primary = models.TextField()      # URL / target path / cookie host / login origin
    secondary = models.TextField(blank=True)   # title / source URL / cookie name / username
    event_time = models.DateTimeField(null=True, blank=True, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    page_no = models.IntegerField(null=True, blank=True)
    offset = models.IntegerField(null=True, blank=True)
    rowid = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-event_time", "id"]
        indexes = [models.Index(fields=["evidence", "kind"])]


class StateItem(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="state_items")
    category = models.CharField(max_length=12, db_index=True)    # session | bookmark | extension | preference | network
    browser = models.CharField(max_length=16)
    name = models.TextField()
    value = models.TextField(blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="present", db_index=True)
    source_file = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["category", "-timestamp", "id"]
        indexes = [models.Index(fields=["evidence", "category"])]


class DnsEntry(models.Model):
    class Origin(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded evidence"
        LOCAL = "local_machine", "This computer (live)"
        LOOKUP = "active_lookup", "Active lookup"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="dns_entries")
    evidence = models.ForeignKey(EvidenceItem, null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="dns_entries")
    origin = models.CharField(max_length=14, choices=Origin.choices, db_index=True)
    entry_type = models.CharField(max_length=14, db_index=True)   # hosts | cache | resolver | search_domain | dns_setting | lookup
    name = models.TextField()
    value = models.TextField(blank=True)
    record_type = models.CharField(max_length=10, blank=True)
    ttl = models.IntegerField(null=True, blank=True)
    flag = models.CharField(max_length=24, blank=True, db_index=True)
    severity = models.CharField(max_length=8, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["entry_type", "name", "id"]
        indexes = [models.Index(fields=["case", "entry_type"])]
