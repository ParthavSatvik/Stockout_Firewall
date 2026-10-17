"""Sarvam AI speech-to-text adapter.

Only active when SARVAM_API_KEY is configured. There is no synthetic/fake transcript
path here -- per the brief, "Never show simulated transcription as real API output".
If the key is absent, the API layer must fall back to text input and say so
explicitly; it must not call this module.

Base URL and request shape follow docs.sarvam.ai as read on 2026-10-16
(docs/PROVIDER_NOTES.md); the exact base URL was not stated on the readable page and
is marked VERIFY there -- confirm against a live key before production use.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings

settings = get_settings()


class SarvamNotConfiguredError(RuntimeError):
    pass


@dataclass
class TranscriptionResult:
    transcript: str
    language_code: str
    language_probability: float | None
    request_id: str


def transcribe(audio_bytes: bytes, filename: str, language_code: str = "unknown") -> TranscriptionResult:
    if not settings.sarvam_configured:
        raise SarvamNotConfiguredError("SARVAM_API_KEY is not configured")

    url = f"{settings.sarvam_base_url}/speech-to-text"
    headers = {"api-subscription-key": settings.sarvam_api_key}
    files = {"file": (filename, audio_bytes)}
    data = {"model": settings.sarvam_stt_model, "language_code": language_code}

    resp = httpx.post(url, headers=headers, files=files, data=data, timeout=30.0)
    resp.raise_for_status()
    body = resp.json()
    return TranscriptionResult(
        transcript=body.get("transcript", ""),
        language_code=body.get("language_code", language_code),
        language_probability=body.get("language_probability"),
        request_id=body.get("request_id", ""),
    )


CHAT_MODEL = "sarvam-105b"  # docs.sarvam.ai/api-reference/chat/chat-completions-v1 (checked 2026-10-17)


def extract_order_items(text: str, product_names: list[str]) -> list[dict]:
    """LLM assist for free-text orders the deterministic parser could not read.
    Returns [{"product": <one of product_names>, "quantity": float, "unit": str}].
    The caller must validate every item and require merchant confirmation."""
    import json

    if not settings.sarvam_configured:
        raise SarvamNotConfiguredError("SARVAM_API_KEY is not configured")
    system = ("You extract wholesale grocery order lines from Indian shopkeepers' messages, which may mix English, Hindi, "
              "Kannada, Tamil, Telugu or Bengali in any script. Reply with JSON only: "
              '{"items":[{"product":"<exact name from the list>","quantity":<number>,"unit":"kg|litre|piece"}]}. '
              "Use only these product names: " + ", ".join(product_names) + ". Skip anything not in the list. Never guess quantities.")
    resp = httpx.post(
        f"{settings.sarvam_base_url}/v1/chat/completions",
        headers={"api-subscription-key": settings.sarvam_api_key, "Authorization": f"Bearer {settings.sarvam_api_key}"},
        json={"model": CHAT_MODEL, "temperature": 0, "max_tokens": 400, "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": text[:2000]}]},
        timeout=30.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content") or "{}"
    data = json.loads(content)
    return data.get("items", []) if isinstance(data, dict) else []
