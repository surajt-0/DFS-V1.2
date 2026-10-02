from django.urls import path

from . import api

app_name = "evidence_api"

urlpatterns = [
    path("case/<int:case_pk>/upload/", api.EvidenceUploadAPI.as_view(), name="upload"),
    path("case/<int:case_pk>/scan-local/", api.LocalScanAPI.as_view(), name="scan_local"),
    path("case/<int:case_pk>/table/<str:kind>/", api.ArtifactTableAPI.as_view(), name="artifact_table"),
    path("demo-case/", api.DemoCaseAPI.as_view(), name="demo_case"),
    path("<int:pk>/", api.EvidenceDetailAPI.as_view(), name="detail"),
    path("<int:pk>/reparse/", api.EvidenceReparseAPI.as_view(), name="reparse"),
]
