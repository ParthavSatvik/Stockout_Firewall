"""Regression tests for defects found in the QA audit (each reproduced before the fix)."""
import pytest

from app.seed import seed_data
from tests.conftest import auth_headers, login


@pytest.fixture(autouse=True)
def fresh_seed():
    seed_data.run()
    yield


def m(client):
    return auth_headers(login(client, "merchant1@example.com"))


def parse(client, text):
    r = client.post("/api/orders/parse-text", headers=m(client), json={"text": text})
    assert r.status_code == 200, r.text
    return [(i["product_name"], i["quantity_base_unit"]) for i in r.json()["items"]], r.json()


@pytest.mark.parametrize("text, expected", [
    ("೧೦೦ ಕೆಜಿ ಅಕ್ಕಿ", [("Rice", 100.0)]),                 # Kannada digits, unit and product
    ("१०० किलो चावल", [("Rice", 100.0)]),                  # Devanagari
    ("20 கிலோ சர்க்கரை", [("Sugar", 20.0)]),              # Tamil
    ("5 లీటర్ నూనె", [("Sunflower Oil", 5.0)]),           # Telugu
    ("১০ কেজি চাল", [("Rice", 10.0)]),                     # Bengali digits
    ("nanage 100 kg akki beku", [("Rice", 100.0)]),        # existing romanised path unchanged
])
def test_indic_scripts_parse(client, text, expected):
    assert parse(client, text)[0] == expected


def test_decomposed_unicode_is_normalised(client):
    import unicodedata
    assert parse(client, unicodedata.normalize("NFD", "೧೦೦ ಕೆಜಿ ಅಕ್ಕಿ"))[0] == [("Rice", 100.0)]


def test_zero_quantity_is_not_an_order_line(client):
    items, body = parse(client, "0 kg akki")
    assert items == [] and body["unmatched_fragments"] == ["0 kg"] and body["requires_confirmation"]


def test_text_fields_are_bounded_to_column_sizes(client):
    h = m(client)
    rice = next(p["id"] for p in client.get("/api/products", headers=h).json() if p["name"] == "Rice")
    line = {"product_id": rice, "requested_qty_base_unit": 10}
    assert client.post("/api/orders", headers=h, json={"items": [{**line, "notes": "x" * 301}]}).status_code == 422
    assert client.post("/api/orders", headers=h, json={"items": [line], "raw_input_language": "y" * 11}).status_code == 422
    assert client.post("/api/orders", headers=h, json={"items": [line], "raw_input_text": "a" * 5001}).status_code == 422
    assert client.post("/api/orders", headers=h, json={"items": [line], "preferred_supplier_ids": ["s"] * 21}).status_code == 422
    assert client.post("/api/orders/parse-text", headers=h, json={"text": "a" * 5001}).status_code == 422
    r = client.post("/api/auth/register", json={"email": "long@example.com", "password": "longenough1", "full_name": "n" * 201,
                                                "role": "merchant", "business_name": "b", "city": "c"})
    assert r.status_code == 422


def test_emails_are_case_insensitive(client):
    body = {"password": "longenough1", "full_name": "T", "role": "merchant", "business_name": "B", "city": "C"}
    assert client.post("/api/auth/register", json={**body, "email": "Mixed.Case@Example.com"}).status_code == 201
    assert client.post("/api/auth/login", json={"email": "mixed.case@example.com", "password": "longenough1"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "MIXED.CASE@EXAMPLE.COM", "password": "longenough1"}).status_code == 200
    assert client.post("/api/auth/register", json={**body, "email": "MIXED.case@example.com"}).status_code == 409


def test_regenerating_plans_replaces_unapproved_alternatives(client):
    h = m(client)
    rice = next(p["id"] for p in client.get("/api/products", headers=h).json() if p["name"] == "Rice")
    order = client.post("/api/orders", headers=h, json={"items": [{"product_id": rice, "requested_qty_base_unit": 50}], "min_reliability": 0.3}).json()
    first = {p["id"] for p in client.post(f"/api/orders/{order['id']}/plan", headers=h).json()["plans"]}
    second = {p["id"] for p in client.post(f"/api/orders/{order['id']}/plan", headers=h).json()["plans"]}
    current = client.get(f"/api/orders/{order['id']}", headers=h).json()["plans"]
    assert len(current) == 3 and {p["id"] for p in current} == second and not first & second


def test_login_is_rate_limited(client, monkeypatch):
    from app.config import get_settings
    from app.ratelimit import limiter
    monkeypatch.setattr(get_settings(), "login_rate_limit", "2/minute")
    limiter.reset()
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong"}).status_code for _ in range(3)]
    limiter.reset()
    assert codes == [401, 401, 429]


def test_provider_outage_and_malformed_webhook_are_clean_errors(client, monkeypatch):
    import hashlib
    import hmac

    import httpx

    from app.config import get_settings
    from app.providers import razorpay
    s = get_settings()
    for k, v in dict(razorpay_key_id="rzp_test_x", razorpay_key_secret="k", razorpay_webhook_secret="w").items():
        monkeypatch.setattr(s, k, v)

    def down(*a, **k):
        raise httpx.ConnectTimeout("timed out")
    monkeypatch.setattr(razorpay.httpx, "post", down)
    h = m(client)
    rice = next(p["id"] for p in client.get("/api/products", headers=h).json() if p["name"] == "Rice")
    order = client.post("/api/orders", headers=h, json={"items": [{"product_id": rice, "requested_qty_base_unit": 50}], "min_reliability": 0.3}).json()
    plan = client.post(f"/api/orders/{order['id']}/plan", headers=h).json()["plans"][0]
    client.post(f"/api/orders/{order['id']}/select-plan", headers=h, json={"plan_id": plan["id"]})
    r = client.post("/api/payments/razorpay/order", headers=h, json={"order_id": order["id"]})
    assert r.status_code == 503 and "unreachable" in r.json()["detail"]

    raw = b"{not json"
    sig = hmac.new(b"w", raw, hashlib.sha256).hexdigest()
    assert client.post("/api/payments/razorpay/webhook", content=raw, headers={"x-razorpay-signature": sig}).status_code == 400


def test_integration_status_requires_login(client):
    assert client.get("/api/integrations/status").status_code == 401
    assert client.get("/api/integrations/status", headers=m(client)).status_code == 200


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    evil = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in evil.headers
