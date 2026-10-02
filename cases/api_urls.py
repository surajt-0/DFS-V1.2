from django.urls import path

from . import api

app_name = "cases_api"

urlpatterns = [
    path("", api.CaseListCreateAPI.as_view(), name="list_create"),
    path("<int:pk>/", api.CaseDetailAPI.as_view(), name="detail"),
    path("<int:pk>/status/<str:new_status>/", api.CaseStatusAPI.as_view(), name="set_status"),
    path("<int:pk>/report/", api.CaseReportPdfAPI.as_view(), name="report_pdf"),
]
