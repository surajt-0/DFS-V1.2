from django.conf import settings
from django.db import models

from cases.models import Case


class EvidenceItem(models.Model):
    class EvidenceType(models.TextChoices):
        CHROMIUM_HISTORY = "chromium_history", "Chromium History (Chrome/Edge/Brave/Opera)"
        CHROMIUM_LOGINS = "chromium_logins", "Chromium Login Data"
        CHROMIUM_COOKIES = "chromium_cookies", "Chromium Cookies"
        CHROMIUM_DOWNLOADS = "chromium_downloads", "Chromium Downloads (from History DB)"
        FIREFOX_HISTORY = "firefox_history", "Firefox places.sqlite"
        FIREFOX_LOGINS = "firefox_logins", "Firefox logins.json"
        FIREFOX_COOKIES = "firefox_cookies", "Firefox cookies.sqlite"
        SAFARI_HISTORY = "safari_history", "Safari History.db"
        CACHE_ARCHIVE = "cache_archive", "Cache folder (.zip, metadata only)"
        BROWSER_STATE = "browser_state", "Browser system data (sessions, bookmarks, preferences, ...)"
        DNS_DATA = "dns_data", "DNS data (hosts file / DNS cache / resolver export)"
        OTHER = "other", "Other / unclassified"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PARSING = "parsing", "Parsing"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Parse failed"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="evidence_items")
    evidence_type = models.CharField(max_length=32, choices=EvidenceType.choices)
    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    size_bytes = models.BigIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    parse_error = models.TextField(blank=True)
    row_count = models.IntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_evidence")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    source_browser_hint = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.get_evidence_type_display()})"

    TABLE_URL_NAME = {
        EvidenceType.CHROMIUM_HISTORY: "evidence:history_table",
        EvidenceType.FIREFOX_HISTORY: "evidence:history_table",
        EvidenceType.SAFARI_HISTORY: "evidence:history_table",
        EvidenceType.CHROMIUM_LOGINS: "evidence:login_table",
        EvidenceType.FIREFOX_LOGINS: "evidence:login_table",
        EvidenceType.CHROMIUM_COOKIES: "evidence:cookie_table",
        EvidenceType.FIREFOX_COOKIES: "evidence:cookie_table",
        EvidenceType.CHROMIUM_DOWNLOADS: "evidence:download_table",
        EvidenceType.CACHE_ARCHIVE: "evidence:cache_table",
    }

    @property
    def table_url_name(self):
        return self.TABLE_URL_NAME.get(self.evidence_type)

    @property
    def artifact_kind(self):
        """Which normalized table this evidence type parses into."""
        t = self.evidence_type
        if t in (self.EvidenceType.CHROMIUM_HISTORY, self.EvidenceType.FIREFOX_HISTORY, self.EvidenceType.SAFARI_HISTORY):
            return "history"
        if t in (self.EvidenceType.CHROMIUM_LOGINS, self.EvidenceType.FIREFOX_LOGINS):
            return "login"
        if t in (self.EvidenceType.CHROMIUM_COOKIES, self.EvidenceType.FIREFOX_COOKIES):
            return "cookie"
        if t == self.EvidenceType.CHROMIUM_DOWNLOADS:
            return "download"
        if t == self.EvidenceType.CACHE_ARCHIVE:
            return "cache"
        if t == self.EvidenceType.BROWSER_STATE:
            return "state"
        if t == self.EvidenceType.DNS_DATA:
            return "dns"
        return None


class HistoryEntry(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="history_entries")
    url = models.TextField()
    title = models.CharField(max_length=500, blank=True)
    visit_count = models.IntegerField(default=0)
    last_visit_time = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["evidence", "last_visit_time"])]


class LoginEntry(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="login_entries")
    site = models.TextField()
    username = models.CharField(max_length=300, blank=True)
    password_value = models.CharField(max_length=50, default="Protected")
    date_created = models.DateTimeField(null=True, blank=True)


class CookieEntry(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="cookie_entries")
    host = models.CharField(max_length=300)
    name = models.CharField(max_length=200, blank=True)
    path = models.CharField(max_length=300, blank=True)
    expires_utc = models.DateTimeField(null=True, blank=True)
    is_secure = models.BooleanField(default=False)
    is_httponly = models.BooleanField(default=False)
    last_access_utc = models.DateTimeField(null=True, blank=True)
    value = models.CharField(max_length=50, default="Protected")


class DownloadEntry(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="download_entries")
    target_path = models.TextField(blank=True)
    source_url = models.TextField(blank=True)
    referrer = models.TextField(blank=True)
    total_bytes = models.BigIntegerField(default=0)
    state = models.CharField(max_length=50, blank=True)
    danger_type = models.CharField(max_length=50, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)


class CacheEntry(models.Model):
    evidence = models.ForeignKey(EvidenceItem, on_delete=models.CASCADE, related_name="cache_entries")
    name = models.CharField(max_length=300)
    path = models.TextField(blank=True)
    mime_guess = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    modified = models.DateTimeField(null=True, blank=True)
