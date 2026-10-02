from django.contrib import admin

from .models import CacheEntry, CookieEntry, DownloadEntry, EvidenceItem, HistoryEntry, LoginEntry


@admin.register(EvidenceItem)
class EvidenceItemAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "case", "evidence_type", "status", "row_count", "uploaded_at")
    list_filter = ("evidence_type", "status")
    search_fields = ("original_filename", "sha256", "case__case_number")


admin.site.register(HistoryEntry)
admin.site.register(LoginEntry)
admin.site.register(CookieEntry)
admin.site.register(DownloadEntry)
admin.site.register(CacheEntry)
