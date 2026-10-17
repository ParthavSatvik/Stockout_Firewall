"""Payment provider abstraction.

`SimulatedPaymentProvider` is the default and is always available -- it never moves
real money and is clearly labelled `is_simulated=True` everywhere it surfaces.

`PaytmStagingProvider` implements Paytm's documented staging Initiate Transaction flow
and checksum algorithm (SHA-256 digest + AES-128-CBC encryption, the algorithm
published across Paytm's official client libraries). It is only used when
PAYTM_MID / PAYTM_MERCHANT_KEY are configured, and its correctness against a live
sandbox has NOT been verified in this session (no credentials were available) --
see docs/PROVIDER_NOTES.md. Treat it as implemented-but-unverified.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import get_settings

settings = get_settings()

PAYTM_FIXED_IV = b"@@@@&&&&####$$$$"  # published constant used by Paytm's own checksum libraries


@dataclass
class PaymentInitiationResult:
    provider_order_id: str
    status: str  # "pending" | "success" | "failed"
    provider_txn_id: str | None
    raw_response: dict
    is_simulated: bool


class PaymentProvider(ABC):
    @abstractmethod
    def initiate(self, order_id: str, amount_inr: float, customer_id: str) -> PaymentInitiationResult: ...

    @abstractmethod
    def verify_status(self, provider_order_id: str) -> str: ...


class SimulatedPaymentProvider(PaymentProvider):
    """Deterministic fake gateway for the local demo. Amounts are never charged.

    To let the demo show a failed-payment path without randomness, any amount whose
    paise value ends in '13' is treated as a simulated decline -- this is documented,
    deterministic, and only active in this simulated provider.
    """

    def initiate(self, order_id: str, amount_inr: float, customer_id: str) -> PaymentInitiationResult:
        provider_order_id = f"SIM-{uuid.uuid4().hex[:12]}"
        paise = round(amount_inr * 100)
        declined = str(paise).endswith("13")
        return PaymentInitiationResult(
            provider_order_id=provider_order_id,
            status="failed" if declined else "success",
            provider_txn_id=f"SIMTXN-{uuid.uuid4().hex[:10]}" if not declined else None,
            raw_response={"simulated": True, "amount": amount_inr, "declined": declined},
            is_simulated=True,
        )

    def verify_status(self, provider_order_id: str) -> str:
        # Simulated transactions resolve synchronously in initiate(); nothing to poll.
        return "success"


class PaytmStagingProvider(PaymentProvider):
    def __init__(self) -> None:
        if not settings.paytm_configured:
            raise RuntimeError("Paytm provider requires PAYTM_MID and PAYTM_MERCHANT_KEY")
        self.mid = settings.paytm_mid
        self.merchant_key = settings.paytm_merchant_key
        self.website = settings.paytm_website
        self.callback_url = settings.paytm_callback_url
        self.base_url = (
            "https://securestage.paytmpayments.com"
            if settings.paytm_env == "staging"
            else "https://secure.paytmpayments.com"
        )

    def _checksum(self, body_json: str) -> str:
        salt = secrets.token_hex(2)  # 4 hex chars, matches Paytm's documented salt length
        to_hash = f"{body_json}|{salt}"
        hashed = hashlib.sha256(to_hash.encode("utf-8")).hexdigest()
        final_string = hashed + salt

        key = self.merchant_key.encode("utf-8")[:16].ljust(16, b"\0")
        padder = padding.PKCS7(128).padder()
        padded = padder.update(final_string.encode("utf-8")) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(PAYTM_FIXED_IV))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(encrypted).decode("utf-8")

    def initiate(self, order_id: str, amount_inr: float, customer_id: str) -> PaymentInitiationResult:
        import json

        body = {
            "requestType": "Payment",
            "mid": self.mid,
            "websiteName": self.website,
            "orderId": order_id,
            "callbackUrl": self.callback_url,
            "txnAmount": {"value": f"{amount_inr:.2f}", "currency": "INR"},
            "userInfo": {"custId": customer_id},
        }
        body_json = json.dumps(body, separators=(",", ":"))
        signature = self._checksum(body_json)
        payload = {"body": body, "head": {"signature": signature}}

        url = f"{self.base_url}/theia/api/v1/initiateTransaction?mid={self.mid}&orderId={order_id}"
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            data = resp.json()
        except httpx.HTTPError as exc:
            return PaymentInitiationResult(
                provider_order_id=order_id,
                status="failed",
                provider_txn_id=None,
                raw_response={"error": str(exc)},
                is_simulated=False,
            )

        txn_token = data.get("body", {}).get("txnToken")
        status = "pending" if txn_token else "failed"
        return PaymentInitiationResult(
            provider_order_id=order_id,
            status=status,
            provider_txn_id=txn_token,
            raw_response=data,
            is_simulated=False,
        )

    def verify_status(self, provider_order_id: str) -> str:
        # Transaction Status API path/response shape was not readable in docs during
        # this session (see docs/PROVIDER_NOTES.md) -- VERIFY against live docs before
        # relying on this in production. Never trust a browser redirect as proof of payment.
        url = f"{self.base_url}/v3/order/status"
        body = {"mid": self.mid, "orderId": provider_order_id}
        import json

        body_json = json.dumps(body, separators=(",", ":"))
        signature = self._checksum(body_json)
        payload = {"body": body, "head": {"signature": signature}}
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            data = resp.json()
        except httpx.HTTPError:
            return "pending"
        result_status = data.get("body", {}).get("resultInfo", {}).get("resultStatus", "")
        if result_status == "TXN_SUCCESS":
            return "success"
        if result_status == "TXN_FAILURE":
            return "failed"
        return "pending"


def get_payment_provider() -> PaymentProvider:
    if settings.paytm_configured and not settings.demo_mode:
        return PaytmStagingProvider()
    return SimulatedPaymentProvider()
