"""Razorpay webhook receiver.

This is a server-to-server endpoint that Razorpay's servers POST to
directly (never a browser) -- it stays outside /api/ and CSRF-exempt like
any other payment-gateway webhook, and is NOT part of the client-facing
surface. Configure it in the Razorpay dashboard as:
    https://<your-domain>/billing/webhook/razorpay/
Safe no-op if RAZORPAY_WEBHOOK_SECRET isn't set (demo-mode deployments).
"""
import json

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import razorpay_client
from .api import _activate_subscription
from .models import Payment


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not razorpay_client.verify_webhook_signature(request.body, signature):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body.decode("utf-8"))
    except ValueError:
        return HttpResponseBadRequest("Bad JSON")

    event_type = event.get("event", "")
    payload = event.get("payload", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    order_id = payment_entity.get("order_id")

    if event_type == "payment.captured" and order_id:
        payment = Payment.objects.filter(razorpay_order_id=order_id).first()
        if payment and payment.status != Payment.Status.PAID:
            payment.status = Payment.Status.PAID
            payment.razorpay_payment_id = payment_entity.get("id", "")
            payment.save(update_fields=["status", "razorpay_payment_id"])
            _activate_subscription(payment.organization, payment.plan, payment.billing_cycle)
    elif event_type == "payment.failed" and order_id:
        Payment.objects.filter(razorpay_order_id=order_id).update(status=Payment.Status.FAILED)

    return JsonResponse({"received": True})
