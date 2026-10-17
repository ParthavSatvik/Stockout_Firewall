"""Provider integrations with the network stubbed: these prove our signature checks,
idempotency, authorization and state transitions -- not that the live providers answer."""
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app import security
from app.config import get_settings
from app.database import SessionLocal
from app.models.ops import OutboundMessage, Payment
from app.models.orders import Order
from app.providers import razorpay, sarvam, whatsapp
from app.routers import integrations
from app.seed import seed_data
from tests.conftest import auth_headers, future, login


@pytest.fixture(autouse=True)
def fresh_seed():
    seed_data.run()
    yield


@pytest.fixture
def cfg(monkeypatch):
    s = get_settings()

    def set_(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(s, k, v)
    return set_


def merchant(client):
    return auth_headers(login(client, "merchant1@example.com"))


def planned_rice_order(client, qty=100):
    m = merchant(client)
    rice = next(p["id"] for p in client.get("/api/products", headers=m).json() if p["name"] == "Rice")
    order = client.post("/api/orders", headers=m, json={"items": [{"product_id": rice, "requested_qty_base_unit": qty}],
                                                         "price_tolerance_pct": 20, "min_reliability": 0.3, "budget_cap": 6000}).json()
    plans = client.post(f"/api/orders/{order['id']}/plan", headers=m).json()["plans"]
    cheapest = next(p for p in plans if p["objective_profile"] == "cheapest")
    client.post(f"/api/orders/{order['id']}/select-plan", headers=m, json={"plan_id": cheapest["id"]})
    return order["id"], m, cheapest


# --------------------------------------------------------------------- Razorpay

RZP = dict(razorpay_key_id="rzp_test_unit", razorpay_key_secret="unit-secret", razorpay_webhook_secret="hook-secret")


def sign(secret, msg: bytes):
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def test_razorpay_order_verify_and_webhook(client, cfg, monkeypatch):
    cfg(**RZP)
    created = []
    monkeypatch.setattr(razorpay, "create_order", lambda amount, receipt, notes: created.append(amount) or {"id": f"order_U{len(created)}", "amount": amount, "currency": "INR"})
    order_id, m, plan = planned_rice_order(client)
    assert client.get("/api/payments/config", headers=m).json() == {"provider": "razorpay", "mode": "test", "key_id": "rzp_test_unit"}
    assert client.post("/api/payments/initiate", headers=m, json={"order_id": order_id}).status_code == 409  # no simulated path

    first = client.post("/api/payments/razorpay/order", headers=m, json={"order_id": order_id}).json()
    again = client.post("/api/payments/razorpay/order", headers=m, json={"order_id": order_id}).json()
    assert first["payment_id"] == again["payment_id"] and len(created) == 1  # idempotent
    assert first["amount"] == round(plan["total_cost"] * 100)

    body = {"payment_id": first["payment_id"], "razorpay_order_id": "order_U1", "razorpay_payment_id": "pay_1"}
    bad = client.post("/api/payments/razorpay/verify", headers=m, json={**body, "razorpay_signature": "0" * 64})
    assert bad.status_code == 400
    # A valid signature for a *different* order id must not be accepted for this payment.
    forged = client.post("/api/payments/razorpay/verify", headers=m, json={**body, "razorpay_order_id": "order_X",
                         "razorpay_signature": sign("unit-secret", b"order_X|pay_1")})
    assert forged.status_code == 400
    with SessionLocal() as db:
        assert db.get(Payment, first["payment_id"]).status.value == "pending"

    ok = client.post("/api/payments/razorpay/verify", headers=m, json={**body, "razorpay_signature": sign("unit-secret", b"order_U1|pay_1")})
    assert ok.json() == {"payment_id": first["payment_id"], "status": "success", "provider_txn_id": "pay_1"}

    failed_event = json.dumps({"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_2", "order_id": "order_U1"}}}}).encode()
    hdr = {"x-razorpay-signature": sign("hook-secret", failed_event), "x-razorpay-event-id": "evt_1", "content-type": "application/json"}
    assert client.post("/api/payments/razorpay/webhook", content=failed_event, headers=hdr).json()["status"] == "success"  # never downgraded
    assert client.post("/api/payments/razorpay/webhook", content=failed_event, headers=hdr).json()["duplicate"] is True
    assert client.post("/api/payments/razorpay/webhook", content=failed_event, headers={**hdr, "x-razorpay-signature": "bad"}).status_code == 400
    assert client.post("/api/payments/razorpay/order", headers=m, json={"order_id": order_id}).status_code == 409


def test_razorpay_webhook_amount_mismatch_is_not_paid(client, cfg, monkeypatch):
    cfg(**RZP)
    monkeypatch.setattr(razorpay, "create_order", lambda amount, receipt, notes: {"id": "order_M", "amount": amount})
    order_id, m, _ = planned_rice_order(client)
    pid = client.post("/api/payments/razorpay/order", headers=m, json={"order_id": order_id}).json()["payment_id"]
    ev = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_M", "amount": 100}}}}).encode()
    r = client.post("/api/payments/razorpay/webhook", content=ev, headers={"x-razorpay-signature": sign("hook-secret", ev), "x-razorpay-event-id": "evt_m"})
    assert r.json()["status"] == "pending"
    with SessionLocal() as db:
        assert db.get(Payment, pid).raw_provider_response["amount_mismatch"] == 100


def test_live_keys_need_explicit_enablement(client, cfg):
    cfg(razorpay_key_id="rzp_live_unit", razorpay_key_secret="s", payments_live_enabled=False)
    order_id, m, _ = planned_rice_order(client)
    assert client.get("/api/payments/config", headers=m).json()["provider"] == "simulated"
    r = client.post("/api/payments/razorpay/order", headers=m, json={"order_id": order_id})
    assert r.status_code == 503 and "PAYMENTS_LIVE_ENABLED" in r.json()["detail"]


# ---------------------------------------------------------------- WhatsApp

TW = dict(twilio_auth_token="tw-token", public_base_url="https://sf.example.com", twilio_account_sid="AC1",
          twilio_api_key_sid="SK1", twilio_api_key_secret="sk-secret", twilio_whatsapp_from="whatsapp:+14155238886")
URL = "https://sf.example.com/api/whatsapp/inbound"


def opt_in(client, phone="+919800000001"):
    r = client.put("/api/auth/me/contact", headers=merchant(client), json={"phone_e164": phone, "whatsapp_opt_in": True})
    assert r.status_code == 200, r.text


def inbound(client, body, sid=None, phone="+919800000001", signature=None):
    params = {"MessageSid": sid or f"SM{uuid.uuid4().hex}", "From": f"whatsapp:{phone}", "Body": body, "NumMedia": "0"}
    sig = signature or whatsapp.expected_signature("tw-token", URL, params)
    return client.post("/api/whatsapp/inbound", data=params, headers={"X-Twilio-Signature": sig})


def test_whatsapp_order_then_confirm(client, cfg, monkeypatch):
    cfg(**TW)
    sent = []
    monkeypatch.setattr(whatsapp, "send", lambda to, body: sent.append((to, body)) or f"SM{len(sent)}")
    opt_in(client)
    r = inbound(client, "nanage 100 kg akki beku")
    assert r.status_code == 200 and "Reply YES" in r.text and "Rice" in r.text
    with SessionLocal() as db:
        order = db.query(Order).filter(Order.raw_input_text.like("[WhatsApp]%")).one()
        assert order.status.value == "planned"
    assert "Confirmed order" in inbound(client, "YES").text
    with SessionLocal() as db:
        assert db.get(Order, order.id).status.value == "awaiting_confirmation"
    # Suppliers were notified of the new request (only if opted in; seeded suppliers are not).
    with SessionLocal() as db:
        assert db.query(OutboundMessage).filter_by(kind="new_request", status="skipped").count() >= 1


def test_whatsapp_rejects_forgery_and_duplicates(client, cfg):
    cfg(**TW)
    opt_in(client)
    assert inbound(client, "100 kg akki", signature="forged").status_code == 403
    first = inbound(client, "100 kg akki", sid="SMdup")
    second = inbound(client, "100 kg akki", sid="SMdup")
    assert "Reply YES" in first.text and "<Message>" not in second.text
    with SessionLocal() as db:
        assert db.query(Order).filter(Order.raw_input_text.like("[WhatsApp]%")).count() == 1
    assert "not linked" in inbound(client, "100 kg akki", phone="+919811111111").text


def test_failure_alert_is_sent_on_whatsapp_after_replan(client, cfg, monkeypatch):
    cfg(**TW)
    sent = []
    monkeypatch.setattr(whatsapp, "send", lambda to, body: sent.append((to, body)) or "SMok")
    opt_in(client)
    order_id, m, plan = planned_rice_order(client)
    line = plan["allocations"][0]
    sh = auth_headers(login(client, "newco@example.com"))
    r = client.post(f"/api/allocations/{line['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 40, "ready_by": future(4)})
    assert r.status_code == 200
    alerts = [(to, b) for to, b in sent if "New plan total" in b]
    assert alerts and alerts[0][0] == "+919800000001" and alerts[0][1].startswith("Stockout Firewall: Order #")
    with SessionLocal() as db:
        msg = db.query(OutboundMessage).filter_by(kind="recovery").one()
        assert (msg.status, msg.provider_sid) == ("sent", "SMok")


def test_failed_send_is_recorded_not_reported_as_sent(client, cfg, monkeypatch):
    cfg(**TW)

    def boom(to, body):
        raise whatsapp.WhatsAppError("Twilio 401: Authenticate")
    monkeypatch.setattr(whatsapp, "send", boom)
    opt_in(client)
    order_id, m, plan = planned_rice_order(client)
    sh = auth_headers(login(client, "newco@example.com"))
    client.post(f"/api/allocations/{plan['allocations'][0]['id']}/reject", headers=sh, json={"reason_code": "out_of_stock"})
    with SessionLocal() as db:
        msg = db.query(OutboundMessage).filter_by(kind="recovery").one()
        assert msg.status == "failed" and "401" in msg.error and msg.provider_sid is None


def test_whatsapp_contact_requires_e164(client):
    m = merchant(client)
    assert client.put("/api/auth/me/contact", headers=m, json={"phone_e164": "98000", "whatsapp_opt_in": True}).status_code == 422
    assert client.put("/api/auth/me/contact", headers=m, json={"whatsapp_opt_in": True}).status_code == 422


# ------------------------------------------------------------------ Sarvam

def test_voice_order_is_transcribed_and_parsed(client, cfg, monkeypatch):
    m = merchant(client)
    files = {"audio": ("order.webm", b"\x1aE\xdf\xa3fake", "audio/webm")}
    assert client.post("/api/orders/transcribe", headers=m, files=files).status_code == 503  # no key: honest refusal
    cfg(sarvam_api_key="sk_unit")
    monkeypatch.setattr(sarvam, "transcribe", lambda data, name, lang: sarvam.TranscriptionResult("nanage 100 kg akki beku", "kn-IN", 0.93, "req_1"))
    body = client.post("/api/orders/transcribe", headers=m, files=files).json()
    assert body["transcript"] == "nanage 100 kg akki beku" and body["source"] == "sarvam"
    assert body["parse"]["items"][0]["product_name"] == "Rice" and body["parse"]["items"][0]["quantity_base_unit"] == 100


# ---------------------------------------------------------------- Supabase

def test_supabase_jwks_token_maps_to_local_role(client, cfg, monkeypatch):
    cfg(supabase_url="https://unit.supabase.co")
    key = ec.generate_private_key(ec.SECP256R1())

    class FakeJWKS:
        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()
    monkeypatch.setattr(security, "_jwks", lambda: FakeJWKS())

    def token(**over):
        now = datetime.now(UTC)
        claims = {"sub": str(uuid.uuid4()), "email": "merchant1@example.com", "aud": "authenticated",
                  "iss": "https://unit.supabase.co/auth/v1", "iat": now, "exp": now + timedelta(hours=1),
                  "user_metadata": {"role": "admin"}, **over}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "unit"})

    me = client.get("/api/auth/me", headers=auth_headers(token()))
    assert me.status_code == 200 and me.json()["role"] == "merchant"  # role from our DB, not token metadata
    expired = token(exp=datetime.now(UTC) - timedelta(minutes=1))
    assert client.get("/api/auth/me", headers=auth_headers(expired)).status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers(token(iss="https://evil.example/auth/v1"))).status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers(token(email="nobody@example.com"))).status_code == 401


# ------------------------------------------------------------------ routing

def test_routes_use_osrm_when_it_answers_and_label_estimates_otherwise(client, monkeypatch):
    integrations._route_cache.clear()
    order_id, m, _ = planned_rice_order(client)

    class Resp:
        status_code = 200

        def json(self):
            return {"code": "Ok", "routes": [{"distance": 15200.0, "duration": 1500.0, "geometry": {"type": "LineString", "coordinates": [[77.5, 12.95], [77.59, 12.97]]}}]}
    monkeypatch.setattr(integrations.httpx, "get", lambda *a, **k: Resp())
    line = client.get(f"/api/orders/{order_id}/routes", headers=m).json()["lines"][0]
    assert line["route"]["source"] == "osrm" and line["route"]["distance_km"] == 15.2 and line["route"]["geometry"]["type"] == "LineString"

    integrations._route_cache.clear()

    def down(*a, **k):
        raise integrations.httpx.ConnectError("offline")
    monkeypatch.setattr(integrations.httpx, "get", down)
    line = client.get(f"/api/orders/{order_id}/routes", headers=m).json()["lines"][0]
    assert line["route"]["source"] == "estimated" and line["route"]["geometry"] is None
