from django.urls import path

from . import webhooks

app_name = "billing"

urlpatterns = [
    path("webhook/razorpay/", webhooks.webhook, name="webhook"),
]
