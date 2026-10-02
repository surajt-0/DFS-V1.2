from django.urls import path

from . import api

app_name = "dashboard_api"

urlpatterns = [
    path("stats/", api.DashboardStatsAPI.as_view(), name="stats"),
]
