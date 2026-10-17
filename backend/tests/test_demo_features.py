"""Dead-Stock both sides, merchant market view, simulated checkout, WhatsApp simulator,
Sarvam LLM assist validation, and that the demo seed fills every merchant screen."""
import pytest

from app.config import get_settings
from app.providers import sarvam
from app.seed import seed_data
from tests.conftest import auth_headers, future, login


@pytest.fixture(autouse=True)
def fresh_seed():
    seed_data.run()
    yield


def h(client, email="merchant1@example.com"):
    return auth_headers(login(client, email))


def pid(client, name):
    return next(p["id"] for p in client.get("/api/products", headers=h(client)).json() if p["name"] == name)


# ------------------------------------------------------------------ seed coverage

def test_seed_fills_every_merchant_screen(client):
    m = h(client)
    for name in ("Rice", "Sugar", "Sunflower Oil"):
        pi = client.get(f"/api/intelligence/price-index?product_id={pid(client, name)}", headers=m).json()
        assert pi["insufficient_data"] is False and pi["avg_price"] is not None and pi["distinct_suppliers"] >= 1
    auto = client.get("/api/intelligence/autopilot-suggestions", headers=m).json()
    assert {"Sugar", "Sunflower Oil", "Tea Powder"} <= {s["product_name"] for s in auto}
    assert "Wheat Atta" not in {s["product_name"] for s in auto}  # bought 4 days ago, not due
    cash = client.get("/api/intelligence/cash-cycle", headers=m).json()
    assert cash["available_cash"] == 25000 and cash["avg_order_cost"] > 300
    leaks = client.get("/api/intelligence/margin-leak", headers=m).json()
    assert len(leaks) >= 5 and any(row["margin_pct"] is not None and row["margin_pct"] < 12 for row in leaks)
    radar = client.get("/api/intelligence/stockout-radar", headers=m).json()
    assert any(r["risk_level"] in ("medium", "high") for r in radar)
    assert client.get("/api/catalog/surplus", headers=m).json()
    # merchant2 stays the honest "new shop" fixture
    assert client.get("/api/intelligence/stockout-radar", headers=h(client, "merchant2@example.com")).json() == []


# ---------------------------------------------------------------- dead stock

def test_dead_stock_works_for_both_sides(client):
    m1, lak = h(client), h(client, "lakshmi@example.com")
    listings = client.get("/api/catalog/surplus", headers=m1).json()
    mine = [x for x in listings if x["is_mine"]]
    theirs = next(x for x in listings if x["product_name"] == "Toor Dal")
    assert mine and mine[0]["pending_offer_count"] == 2          # merchant1's oil listing has two seeded offers
    assert theirs["my_offer"]["status"] == "pending"              # merchant1 already offered on Lakshmi's dal

    # Own listing: offering is refused; others: an offer above the listed quantity is refused.
    assert client.post(f"/api/catalog/surplus/{mine[0]['id']}/offers", headers=m1,
                       json={"qty_requested_base_unit": 1, "offered_price_per_base_unit": 1}).status_code == 400
    assert client.post(f"/api/catalog/surplus/{theirs['id']}/offers", headers=m1,
                       json={"qty_requested_base_unit": 61, "offered_price_per_base_unit": 90}).status_code == 422
    # A second offer revises the pending one instead of duplicating it.
    r = client.post(f"/api/catalog/surplus/{theirs['id']}/offers", headers=m1, json={"qty_requested_base_unit": 40, "offered_price_per_base_unit": 97})
    assert r.status_code == 201 and r.json()["offered_price_per_base_unit"] == 97
    offers = client.get(f"/api/catalog/surplus/{theirs['id']}/offers", headers=lak).json()
    assert len(offers) == 1 and offers[0]["offerer_name"] == "Ganesh Kirana Store"

    # Lister side: decline one, accept another; listing becomes matched and stays visible to both.
    oil = mine[0]
    oil_offers = client.get(f"/api/catalog/surplus/{oil['id']}/offers", headers=m1).json()
    assert client.post(f"/api/catalog/surplus/offers/{oil_offers[0]['id']}/decline", headers=m1).json()["status"] == "declined"
    assert client.post(f"/api/catalog/surplus/offers/{oil_offers[1]['id']}/accept", headers=m1).json()["status"] == "accepted"
    after = next(x for x in client.get("/api/catalog/surplus", headers=m1).json() if x["id"] == oil["id"])
    assert after["status"] == "matched"
    assert client.post(f"/api/catalog/surplus/offers/{oil_offers[0]['id']}/accept", headers=m1).status_code == 409
    assert client.post(f"/api/catalog/surplus/offers/{offers[0]['id']}/accept", headers=m1).status_code == 403  # not the lister


# ------------------------------------------------------------- market view

def test_market_view_shows_free_to_promise_not_safety_stock(client):
    rows = client.get("/api/catalog/offers", headers=h(client)).json()
    assert len({r["product_name"] for r in rows}) >= 8
    atta = next(r for r in rows if r["supplier_name"] == "Anand Wholesale Grains" and r["product_name"] == "Wheat Atta")
    assert atta["free_to_promise_base_unit"] == 20 and atta["stock_qty_base_unit"] == 20  # 80 - 50 committed - 10 safety
    rice_only = client.get(f"/api/catalog/offers?product_id={pid(client, 'Rice')}", headers=h(client)).json()
    assert rice_only and all(r["product_name"] == "Rice" for r in rice_only)


# ---------------------------------------------------------- simulated checkout

def _confirmed_order(client):
    m = h(client)
    order = client.post("/api/orders", headers=m, json={"items": [{"product_id": pid(client, "Rice"), "requested_qty_base_unit": 50}], "min_reliability": 0.3}).json()
    plan = client.post(f"/api/orders/{order['id']}/plan", headers=m).json()["plans"][0]
    client.post(f"/api/orders/{order['id']}/select-plan", headers=m, json={"plan_id": plan["id"]})
    return order["id"], m


def test_simulated_checkout_records_method_receipt_and_decline(client):
    order_id, m = _confirmed_order(client)
    bad = client.post("/api/payments/initiate", headers=m, json={"order_id": order_id, "method": "upi", "instrument": "failure@upi"}).json()
    assert bad["status"] == "failed" and bad["provider_txn_id"] is None and bad["raw_provider_response"]["declined"] is True
    ok = client.post("/api/payments/initiate", headers=m, json={"order_id": order_id, "method": "card", "instrument": "Visa •••• 1111"}).json()
    assert ok["status"] == "success" and ok["is_simulated"] is True
    assert ok["raw_provider_response"]["method"] == "card" and ok["raw_provider_response"]["bank_reference"].startswith("SIMRRN")
    history = client.get(f"/api/payments/order/{order_id}", headers=m).json()
    assert [p["status"] for p in history] == ["success", "failed"]
    assert client.post("/api/payments/initiate", headers=m, json={"order_id": order_id}).status_code == 409  # already paid
    assert client.get(f"/api/payments/order/{order_id}", headers=h(client, "merchant2@example.com")).status_code == 404


# ------------------------------------------------------------ WhatsApp simulator

def test_whatsapp_simulator_runs_the_real_order_flow(client):
    m = h(client)
    r = client.post("/api/whatsapp/simulate", headers=m, json={"text": "25 kg sakkare"})
    assert "Reply YES" in r.json()["reply"] and "Sugar" in r.json()["reply"]
    assert "Confirmed order" in client.post("/api/whatsapp/simulate", headers=m, json={"text": "yes"}).json()["reply"]
    thread = client.get("/api/whatsapp/thread", headers=m).json()
    bodies = [x["body"] for x in thread["messages"]]
    assert "25 kg sakkare" in bodies and any("Confirmed order" in b for b in bodies)
    assert all(x["status"] in ("simulated", "skipped") for x in thread["messages"])  # nothing claims to be sent
    # Unknown products never create an empty order line (previously crashed the webhook).
    assert "could not find" in client.post("/api/whatsapp/simulate", headers=m, json={"text": "100 kg xyzabc"}).json()["reply"]
    assert client.post("/api/whatsapp/simulate", headers=h(client, "anand@example.com"), json={"text": "hi"}).status_code == 403


def test_whatsapp_simulator_is_demo_only(client, monkeypatch):
    headers = h(client)  # log in while demo mode is still on
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert client.post("/api/whatsapp/simulate", headers=headers, json={"text": "25 kg sugar"}).status_code in (401, 403)


# ----------------------------------------------------------- Sarvam LLM assist

def test_llm_assist_only_when_needed_and_always_validated(client, monkeypatch):
    calls = []

    def fake(text, names):
        calls.append(text)
        return [{"product": "Sugar", "quantity": 20, "unit": "kg"}, {"product": "Caviar", "quantity": 1, "unit": "kg"},
                {"product": "Rice", "quantity": -5, "unit": "kg"}, {"product": "Sunflower Oil", "quantity": 3, "unit": "kg"}]
    monkeypatch.setattr(sarvam, "extract_order_items", fake)
    m = h(client)
    # Without a key the LLM is never called.
    body = client.post("/api/orders/parse-text", headers=m, json={"text": "do bori cheeni bhej do"}).json()
    assert body["items"] == [] and body["llm"]["available"] is False and calls == []

    monkeypatch.setattr(get_settings(), "sarvam_api_key", "sk_test_unit")
    assert client.post("/api/orders/parse-text", headers=m, json={"text": "100 kg akki"}).json()["llm"]["used"] is False  # lexicon was sure
    body = client.post("/api/orders/parse-text", headers=m, json={"text": "do bori cheeni bhej do"}).json()
    assert body["llm"]["used"] is True
    assert [(i["product_name"], i["quantity_base_unit"], i["source"]) for i in body["items"]] == [("Sugar", 20.0, "sarvam_llm")]
    assert body["requires_confirmation"] is True  # LLM output is never auto-approved


def test_llm_outage_keeps_deterministic_result(client, monkeypatch):
    import httpx

    def down(text, names):
        raise httpx.ConnectTimeout("down")
    monkeypatch.setattr(sarvam, "extract_order_items", down)
    monkeypatch.setattr(get_settings(), "sarvam_api_key", "sk_test_unit")
    body = client.post("/api/orders/parse-text", headers=h(client), json={"text": "something unclear"}).json()
    assert body["items"] == [] and body["llm"]["error"] == "ConnectTimeout"


def test_relay_and_payment_notifications_reach_the_thread(client):
    order_id, m = _confirmed_order(client)
    client.post("/api/payments/initiate", headers=m, json={"order_id": order_id, "method": "upi", "instrument": "success@upi"})
    thread = client.get("/api/whatsapp/thread", headers=m).json()["messages"]
    assert any("simulated payment" in x["body"] and x["status"] == "skipped" for x in thread)
    assert future()  # helper import kept for parity with other suites
