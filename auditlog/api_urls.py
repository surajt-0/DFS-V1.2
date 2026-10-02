from django.urls import path

from . import api

app_name = "auditlog_api"

urlpatterns = [
    path("", api.AuditLogListAPI.as_view(), name="list"),
]
