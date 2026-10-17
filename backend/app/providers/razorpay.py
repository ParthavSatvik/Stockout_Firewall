"""Razorpay Standard Checkout adapter (Orders API + signature checks), per
razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps.

* Orders are created server-side with the amount in paise; the browser never sets the amount.
* Checkout success is trusted only after HMAC_SHA256(<server order id>|<payment id>, key_secret)
  matches, compared in constant time.
* Webhooks are trusted only after HMAC_SHA256(<raw body>, webhook_secret) matches the
  X-Razorpay-Signature header.
"""
from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import get_settings

API = "https://api.razorpay.com/v1"


class RazorpayError(RuntimeError):
    pass


def _auth() -> tuple[str, str]:
    s = get_settings()
    if not s.razorpay_configured:
        raise RazorpayError("Razorpay keys are not configured")
    if s.razorpay_mode == "live" and not s.payments_live_enabled:
        raise RazorpayError("Live Razorpay keys are present but PAYMENTS_LIVE_ENABLED is false")
    return s.razorpay_key_id, s.razorpay_key_secret


def to_paise(amount_inr: float) -> int:
    return int(round(amount_inr * 100))


def create_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    resp = httpx.post(f"{API}/orders", auth=_auth(), timeout=15.0,
                      json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes})
    if resp.status_code >= 400:
        raise RazorpayError(f"Razorpay order creation failed ({resp.status_code})")
    return resp.json()


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_payment_signature(server_order_id: str, payment_id: str, signature: str) -> bool:
    secret = get_settings().razorpay_key_secret
    if not (secret and server_order_id and payment_id and signature):
        return False
    return hmac.compare_digest(_hmac_hex(secret, f"{server_order_id}|{payment_id}".encode()), signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().razorpay_webhook_secret
    if not (secret and signature):
        return False
    return hmac.compare_digest(_hmac_hex(secret, raw_body), signature)
