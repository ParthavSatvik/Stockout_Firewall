"""Centralized application settings loaded from environment variables / .env.

All provider credentials default to empty strings. Absence of a credential
must never crash the app in demo mode -- it should disable the real adapter
and fall back to a clearly labelled simulated provider instead.
"""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "staging", "production"] = "local"
    demo_mode: bool = True
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    database_url: str = "sqlite:///./stockout.db"

    # Supabase (production auth)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # legacy HS256 projects only
    supabase_publishable_key: str = ""  # public; the frontend uses VITE_SUPABASE_PUBLISHABLE_KEY
    supabase_secret_key: str = ""  # BACKEND ONLY; not needed for request auth
    supabase_jwks_url: str = ""  # defaults to <SUPABASE_URL>/auth/v1/.well-known/jwks.json

    # Local auth fallback (demo/local only)
    local_jwt_secret: str = "change-me-locally-only"
    access_token_expire_minutes: int = 60 * 12
    login_rate_limit: str = "10/minute"

    # Sarvam AI
    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_llm_model: str = ""

    # Gemini (optional)
    gemini_api_key: str = ""

    # Paytm
    paytm_env: Literal["staging", "production"] = "staging"
    paytm_mid: str = ""
    paytm_merchant_key: str = ""
    paytm_website: str = "WEBSTAGING"
    paytm_callback_url: str = "http://localhost:8000/api/payments/paytm/callback"

    # Razorpay (Standard Checkout). Test keys start rzp_test_; live keys additionally
    # need PAYMENTS_LIVE_ENABLED=true so a misplaced live key can never charge silently.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""  # BACKEND ONLY
    razorpay_webhook_secret: str = ""  # BACKEND ONLY
    payments_live_enabled: bool = False

    # Twilio WhatsApp. Outbound uses an API key; inbound webhook signatures use the auth token.
    twilio_account_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""  # BACKEND ONLY
    twilio_auth_token: str = ""  # BACKEND ONLY
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886 (sandbox) or your approved sender
    public_base_url: str = ""  # externally reachable base URL Twilio calls; used to verify signatures

    # Road routing (OSRM HTTP API). The public demo server is for light, non-commercial use.
    osrm_base_url: str = "https://router.project-osrm.org"
    routing_enabled: bool = True

    # Google Maps Routes
    google_maps_api_key: str = ""

    # Observability
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def production_guards(self):
        if self.app_env == "production" and (self.demo_mode or not self.supabase_configured):
            raise ValueError("Production requires DEMO_MODE=false and Supabase authentication")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.sarvam_api_key)

    @property
    def paytm_configured(self) -> bool:
        return bool(self.paytm_mid and self.paytm_merchant_key)

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def razorpay_mode(self) -> str:
        if not self.razorpay_configured:
            return "unconfigured"
        return "live" if self.razorpay_key_id.startswith("rzp_live_") else "test"

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_api_key_sid and self.twilio_api_key_secret and self.twilio_whatsapp_from)

    @property
    def resolved_supabase_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json" if self.supabase_url else ""

    @property
    def google_maps_configured(self) -> bool:
        return bool(self.google_maps_api_key)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and (self.supabase_jwt_secret or self.resolved_supabase_jwks_url))


@lru_cache
def get_settings() -> Settings:
    return Settings()
