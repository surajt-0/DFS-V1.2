from django.urls import path

from . import downloads

app_name = "recovery_downloads"

urlpatterns = [
    path("case/<int:case_pk>/<str:kind>/", downloads.export_recovery, name="export"),
]
