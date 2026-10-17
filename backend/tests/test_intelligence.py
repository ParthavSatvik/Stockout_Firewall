"""Smoke + correctness tests for the intelligence modules (stockout radar, survival
mode, cash-cycle planner, margin leak detector, price index, autopilot, dead-stock
exchange). These are all deterministic computations over real Order/SupplierInventory/
PriceObservation rows -- no LLM, no fabricated confidence.
"""
from tests.conftest import auth_headers, login


def _rice_id(client):
    return next(p["id"] for p in client.get("/api/products").json() if p["name"] == "Rice")


def _sugar_id(client):
    return next(p["id"] for p in client.get("/api/products").json() if p["name"] == "Sugar")


def test_dashboard_summary_smoke(client):
    token = login(client, "merchant1@example.com")
    resp = client.get("/api/intelligence/dashboard-summary", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert "total_spend" in body and "action_feed" in body


def test_stockout_radar_reports_insufficient_data_for_new_merchant(client):
    token = login(client, "merchant2@example.com")  # has no order history in seed data
    resp = client.get("/api/intelligence/stockout-radar", headers=auth_headers(token))
    assert resp.status_code == 200
    # merchant2 has zero fulfilled orders in the seed -> empty radar, never a fabricated risk
    assert resp.json() == []


def test_stockout_radar_uses_real_history_for_seeded_merchant(client):
    token = login(client, "merchant1@example.com")  # has seeded rice order history
    resp = client.get("/api/intelligence/stockout-radar", headers=auth_headers(token))
    assert resp.status_code == 200
    items = resp.json()
    assert items
    rice = next((i for i in items if i["product_name"] == "Rice"), None)
    assert rice is not None
    assert rice["sample_size"] >= 2
    assert rice["insufficient_data"] is False
    assert rice["risk_level"] in ("none", "low", "medium", "high")


def test_survival_mode_respects_budget_and_priority(client):
    token = login(client, "merchant1@example.com")
    rice_id = _rice_id(client)
    sugar_id = _sugar_id(client)
    resp = client.post(
        "/api/intelligence/survival-mode",
        json={
            "items": [
                {"product_id": rice_id, "product_name": "Rice", "requested_qty_base_unit": 100, "priority": 1},
                {"product_id": sugar_id, "product_name": "Sugar", "requested_qty_base_unit": 50, "priority": 2},
            ],
            "budget_cap": 2000,  # deliberately tight: can't fully cover both at this price level
            "price_tolerance_pct": 20,
            "min_reliability": 0.3,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["budget_cap"] == 2000
    assert body["total_spent"] <= 2000 + 1e-6
    assert len(body["tiers"]) == 2
    assert body["tiers"][0]["priority"] == 1  # priority-1 tier solved first


def test_cash_cycle_requires_explicit_input(client):
    token = login(client, "merchant1@example.com")
    resp = client.get("/api/intelligence/cash-cycle", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_cash_input"

    set_resp = client.post(
        "/api/intelligence/cash-cycle/cash-on-hand", json={"available_cash_on_hand": 5000}, headers=auth_headers(token)
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["available_cash"] == 5000


def test_margin_leak_detector_computes_traceable_margin(client):
    token = login(client, "merchant1@example.com")
    rice_id = _rice_id(client)

    empty = client.get("/api/intelligence/margin-leak", headers=auth_headers(token))
    assert empty.status_code == 200 and empty.json() == []

    upsert = client.post(
        "/api/intelligence/selling-prices",
        json={"product_id": rice_id, "selling_price_per_base_unit": 40.0},
        headers=auth_headers(token),
    )
    assert upsert.status_code == 201

    report = client.get("/api/intelligence/margin-leak", headers=auth_headers(token))
    assert report.status_code == 200
    line = report.json()[0]
    assert line["product_id"] == rice_id
    assert line["cheapest_cost_per_base_unit"] is not None
    assert line["margin_pct"] is not None
    # traceable: margin = selling - cheapest cost
    assert abs(line["margin_per_base_unit"] - (40.0 - line["cheapest_cost_per_base_unit"])) < 1e-6


def test_price_index_insufficient_then_populated(client):
    token = login(client, "merchant1@example.com")
    rice_id = _rice_id(client)
    resp = client.get(f"/api/intelligence/price-index?product_id={rice_id}", headers=auth_headers(token))
    assert resp.status_code == 200
    # seeded SupplierInventory upserts never ran through the write-path endpoint, but
    # confirmed allocations from other tests may have populated observations already;
    # either way the response must be well-formed and honest about sample size.
    body = resp.json()
    assert body["product_id"] == rice_id
    if body["insufficient_data"]:
        assert body["avg_price"] is None
    else:
        assert body["avg_price"] is not None


def test_autopilot_suggestions_smoke(client):
    token = login(client, "merchant1@example.com")
    resp = client.get("/api/intelligence/autopilot-suggestions", headers=auth_headers(token))
    assert resp.status_code == 200
    for s in resp.json():
        assert s["sample_size"] >= 2
        assert s["confidence"] in ("low", "medium", "high")


def test_dead_stock_exchange_listing_offer_accept_flow(client):
    merchant_token = login(client, "merchant1@example.com")
    supplier_token = login(client, "anand@example.com")
    rice_id = _rice_id(client)

    create = client.post(
        "/api/catalog/surplus", json={"product_id": rice_id, "qty_base_unit": 15, "asking_price_per_base_unit": 30},
        headers=auth_headers(merchant_token),
    )
    assert create.status_code == 201, create.text
    listing = create.json()
    assert listing["lister_type"] == "merchant"

    listed = client.get("/api/catalog/surplus", headers=auth_headers(supplier_token))
    assert any(item["id"] == listing["id"] for item in listed.json())

    offer = client.post(
        f"/api/catalog/surplus/{listing['id']}/offers",
        json={"qty_requested_base_unit": 10, "offered_price_per_base_unit": 28},
        headers=auth_headers(supplier_token),
    )
    assert offer.status_code == 201, offer.text

    # lister can see offers; the offerer (or anyone else) cannot
    offers_as_lister = client.get(f"/api/catalog/surplus/{listing['id']}/offers", headers=auth_headers(merchant_token))
    assert offers_as_lister.status_code == 200
    assert len(offers_as_lister.json()) == 1

    offers_as_offerer = client.get(f"/api/catalog/surplus/{listing['id']}/offers", headers=auth_headers(supplier_token))
    assert offers_as_offerer.status_code == 403

    accept = client.post(
        f"/api/catalog/surplus/offers/{offer.json()['id']}/accept", headers=auth_headers(merchant_token)
    )
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    still_listed = client.get("/api/catalog/surplus", headers=auth_headers(merchant_token))
    assert not any(item["id"] == listing["id"] for item in still_listed.json())  # matched, no longer open
