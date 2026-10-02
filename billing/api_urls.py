from django.urls import path

from . import api

app_name = "billing_api"

urlpatterns = [
    path("plans/", api.PlanListAPI.as_view(), name="plans"),
    path("me/", api.MeAPI.as_view(), name="me"),
    path("my/", api.MySubscriptionAPI.as_view(), name="my"),
    path("my/modify/", api.SubscriptionModifyAPI.as_view(), name="modify"),
    path("my/cancel/", api.SubscriptionCancelAPI.as_view(), name="cancel"),
    path("my/downgrade-free/", api.DowngradeFreeAPI.as_view(), name="downgrade_free"),
    path("payments/", api.PaymentListAPI.as_view(), name="payments"),
    # NOTE: the /verify/ route must be listed before the generic
    # <plan_key>/<cycle>/ route -- otherwise "checkout/<id>/verify/" gets
    # swallowed by the create route (plan_key=<id>, cycle="verify").
    path("checkout/<int:payment_id>/verify/", api.CheckoutVerifyAPI.as_view(), name="checkout_verify"),
    path("checkout/<str:plan_key>/<str:cycle>/", api.CheckoutCreateAPI.as_view(), name="checkout"),
    path("admin/plans/", api.PlanAdminListAPI.as_view(), name="admin_plans"),
    path("admin/plans/<int:plan_id>/", api.PlanAdminDetailAPI.as_view(), name="admin_plan_detail"),
]
