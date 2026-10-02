from django.urls import path

from . import downloads

app_name = "evidence_downloads"

urlpatterns = [
    path("case/<int:case_pk>/history/", downloads.export_table, {"kind": "history"}, name="export_history"),
    path("case/<int:case_pk>/logins/", downloads.export_table, {"kind": "login"}, name="export_logins"),
    path("case/<int:case_pk>/cookies/", downloads.export_table, {"kind": "cookie"}, name="export_cookies"),
    path("case/<int:case_pk>/downloads/", downloads.export_table, {"kind": "download"}, name="export_downloads"),
    path("case/<int:case_pk>/cache/", downloads.export_table, {"kind": "cache"}, name="export_cache"),
]
