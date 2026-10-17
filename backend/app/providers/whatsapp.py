"""Twilio WhatsApp adapter: outbound Messages API and inbound webhook signature check.

* Outbound: POST /2010-04-01/Accounts/{AccountSid}/Messages.json with HTTP Basic auth using an
  API Key SID/secret (not the account auth token).
* Inbound: X-Twilio-Signature = base64(HMAC-SHA1(auth_token, full_url + sorted(key+value)...)).
  The URL must be exactly what Twilio called, so it is rebuilt from PUBLIC_BASE_URL rather
  than from proxy-rewritten request headers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.config import get_settings


class WhatsAppError(RuntimeError):
    pass


def as_whatsapp(phone_e164: str) -> str:
    return phone_e164 if phone_e164.startswith("whatsapp:") else f"whatsapp:{phone_e164}"


def send(to_phone_e164: str, body: str) -> str:
    """Returns the Twilio message SID. Raises WhatsAppError on any failure."""
    s = get_settings()
    if not s.twilio_configured:
        raise WhatsAppError("Twilio WhatsApp is not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    resp = httpx.post(url, auth=(s.twilio_api_key_sid, s.twilio_api_key_secret), timeout=10.0,
                      data={"From": as_whatsapp(s.twilio_whatsapp_from), "To": as_whatsapp(to_phone_e164), "Body": body[:1600]})
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message", "")
        except ValueError:
            detail = ""
        raise WhatsAppError(f"Twilio {resp.status_code}: {detail}"[:300])
    return resp.json().get("sid", "")


def expected_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def verify_signature(url: str, params: dict[str, str], signature: str) -> bool:
    token = get_settings().twilio_auth_token
    if not (token and signature):
        return False
    return hmac.compare_digest(expected_signature(token, url, params), signature)


def download_media(media_url: str) -> tuple[bytes, str]:
    """Inbound voice notes. Twilio media URLs require account authentication."""
    s = get_settings()
    resp = httpx.get(media_url, auth=(s.twilio_api_key_sid, s.twilio_api_key_secret), timeout=20.0, follow_redirects=True)
    if resp.status_code >= 400:
        raise WhatsAppError(f"Media download failed ({resp.status_code})")
    if len(resp.content) > 5 * 1024 * 1024:
        raise WhatsAppError("Voice note too large")
    return resp.content, resp.headers.get("content-type", "audio/ogg")
