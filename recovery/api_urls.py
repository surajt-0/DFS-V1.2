from django.urls import path

from . import api

app_name = "recovery_api"

urlpatterns = [
    path("case/<int:case_pk>/summary/", api.SummaryAPI.as_view(), name="summary"),
    path("case/<int:case_pk>/carve/", api.CarveAPI.as_view(), name="carve"),
    path("case/<int:case_pk>/deleted/", api.DeletedListAPI.as_view(), name="deleted"),
    path("case/<int:case_pk>/state/", api.StateListAPI.as_view(), name="state"),
    path("case/<int:case_pk>/dns/entries/", api.DnsListAPI.as_view(), name="dns_entries"),
    path("case/<int:case_pk>/dns/domains/", api.DnsDomainsAPI.as_view(), name="dns_domains"),
    path("case/<int:case_pk>/dns/scan-local/", api.DnsLocalScanAPI.as_view(), name="dns_scan_local"),
    path("case/<int:case_pk>/dns/lookup/", api.DnsLookupAPI.as_view(), name="dns_lookup"),
    path("case/<int:case_pk>/dns/clear-lookups/", api.DnsClearLookupsAPI.as_view(), name="dns_clear"),
]
