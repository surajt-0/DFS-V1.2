"""Thin wrapper around the Razorpay SDK.

If DFS_RAZORPAY_KEY_ID / DFS_RAZORPAY_KEY_SECRET are not set, every function
here falls back to a self-consistent "demo mode" so the whole upgrade ->
checkout -> invoice flow is fully clickable in dev / trial deployments
without a live payment gateway. Payments created in demo mode are flagged
with Payment.is_demo=True and clearly labelled in the UI -- they are never
silently treated as real money.
"""
import hashlib
import hmac
import uuid

from django.conf import settings

try:
    import razorpay
except ImportError:  # pragma: no cover - optional dependency
    razorpay = None


def is_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and razorpay is not None)


def get_client():
    if not is_configured():
        return None
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(amount_rupees, currency="INR", receipt=None, notes=None):
    """Returns a dict shaped like a Razorpay Order. In demo mode, fabricates
    one locally so the checkout page still renders and can be "paid"."""
    amount_paise = int(round(float(amount_rupees) * 100))
    client = get_client()
    receipt = receipt or uuid.uuid4().hex[:24]

    if client is None:
        return {
            "id": f"order_DEMO{uuid.uuid4().hex[:14].upper()}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "demo": True,
        }

    order = client.order.create({
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt,
        "notes": notes or {},
        "payment_capture": 1,
    })
    order["demo"] = False
    return order


def verify_payment_signature(order_id, payment_id, signature) -> bool:
    client = get_client()
    if client is None:
        # Demo mode has no real signature to check; the "Simulate payment"
        # button is the only way to reach this path, so trust it.
        return True
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        return True
    except Exception:
        return False


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    generated = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(generated, signature)
