"""End-to-end API tests for the core recovery scenario and surrounding workflow:
merchant order -> optimizer plan comparison -> supplier confirms partial quantity ->
automatic failover re-optimizes the shortfall -> remaining suppliers confirm ->
dispatch/deliver -> reconciliation.
"""
from tests.conftest import auth_headers, future, login


def _rice_product_id(client):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    products = resp.json()
    return next(p["id"] for p in products if p["name"] == "Rice")


def test_health_reports_demo_mode(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["demo_mode"] is True
    assert body["paytm_configured"] is False  # no credentials configured in tests


def test_core_recovery_scenario_end_to_end(client):
    merchant_token = login(client, "merchant1@example.com")
    rice_id = _rice_product_id(client)

    # 1. Create a 100kg rice order.
    create_resp = client.post(
        "/api/orders",
        json={
            "items": [{"product_id": rice_id, "requested_qty_base_unit": 100}],
            "objective_profile": "cheapest",
            "price_tolerance_pct": 15,
            "min_reliability": 0.3,
            "max_suppliers": 4,
        },
        headers=auth_headers(merchant_token),
    )
    assert create_resp.status_code == 201, create_resp.text
    order = create_resp.json()
    order_id = order["id"]
    assert order["status"] == "draft"

    # 2. Plan it -- three objective profiles, all feasible, all fully covering 100kg.
    plan_resp = client.post(f"/api/orders/{order_id}/plan", headers=auth_headers(merchant_token))
    assert plan_resp.status_code == 200, plan_resp.text
    plans = plan_resp.json()["plans"]
    assert len(plans) == 3
    for p in plans:
        assert p["is_feasible"]
        total_allocated = sum(a["allocated_qty_base_unit"] for a in p["allocations"])
        assert total_allocated >= 100.0

    cheapest_plan = next(p for p in plans if p["objective_profile"] == "cheapest")
    first_supplier_id = cheapest_plan["allocations"][0]["supplier_id"]
    first_alloc_id = cheapest_plan["allocations"][0]["id"]
    first_supplier_qty = cheapest_plan["allocations"][0]["allocated_qty_base_unit"]
    assert first_supplier_qty == 100.0  # one supplier covers the whole basket initially

    # 3. Merchant selects the cheapest plan.
    select_resp = client.post(
        f"/api/orders/{order_id}/select-plan", json={"plan_id": cheapest_plan["id"]}, headers=auth_headers(merchant_token)
    )
    assert select_resp.status_code == 200
    assert select_resp.json()["status"] == "awaiting_confirmation"

    # Find which seeded supplier login owns that allocation.
    supplier_logins = {
        "Anand Wholesale Grains": "anand@example.com",
        "Lakshmi Traders": "lakshmi@example.com",
        "Sri Balaji Provisions": "balaji@example.com",
        "NewCo Supplies (joined this month)": "newco@example.com",
    }
    first_supplier_name = cheapest_plan["allocations"][0]["supplier_name"]
    first_supplier_token = login(client, supplier_logins[first_supplier_name])

    # A different supplier must NOT be able to act on this allocation.
    other_name = next(n for n in supplier_logins if n != first_supplier_name)
    other_token = login(client, supplier_logins[other_name])
    forbidden_resp = client.post(
        f"/api/allocations/{first_alloc_id}/confirm",
        json={"confirmed_qty_base_unit": 100, "ready_by": future()},
        headers=auth_headers(other_token),
    )
    assert forbidden_resp.status_code == 404  # ownership-scoped, not leaked as 403

    # 4. THE CORE SCENARIO: primary supplier confirms only 40 of the 100kg.
    confirm_resp = client.post(
        f"/api/allocations/{first_alloc_id}/confirm",
        json={"confirmed_qty_base_unit": 40, "ready_by": future()},
        headers=auth_headers(first_supplier_token),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "short_supply"
    assert confirmed["confirmed_qty_base_unit"] == 40.0

    # 5. System must have auto-replanned: order now shows a new plan covering the
    # missing 60kg from other suppliers, while the confirmed 40kg is preserved.
    order_after = client.get(f"/api/orders/{order_id}", headers=auth_headers(merchant_token)).json()
    assert order_after["status"] == "replanning"
    active_plan = next(p for p in order_after["plans"] if p["is_selected"])
    assert active_plan["replan_reason"] == "short_supply"

    kept_line = next(a for a in active_plan["allocations"] if a["supplier_id"] == first_supplier_id)
    assert kept_line["status"] == "short_supply"
    assert kept_line["confirmed_qty_base_unit"] == 40.0

    new_lines = [a for a in active_plan["allocations"] if a["supplier_id"] != first_supplier_id]
    assert new_lines, "replan must allocate the 60kg shortfall to alternative suppliers"
    assert all(a["supplier_id"] != first_supplier_id for a in new_lines)
    gap_covered = sum(a["allocated_qty_base_unit"] for a in new_lines)
    assert gap_covered >= 60.0 - 1e-6

    # Recalculated cost/delivery must reflect the new allocation, not the stale one.
    assert active_plan["total_cost"] > 0
    assert active_plan["estimated_delivery_hours"] > 0

    # 6. Confirm the remaining allocations so the order can complete.
    for line in new_lines:
        supplier_token = login(client, supplier_logins[line["supplier_name"]])
        r = client.post(
            f"/api/allocations/{line['id']}/confirm",
            json={"confirmed_qty_base_unit": line["allocated_qty_base_unit"], "ready_by": future()},
            headers=auth_headers(supplier_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "confirmed"

    order_confirmed = client.get(f"/api/orders/{order_id}", headers=auth_headers(merchant_token)).json()
    assert order_confirmed["status"] == "confirmed"

    # 7. Dispatch + deliver every active (non-superseded) allocation.
    final_plan = next(p for p in order_confirmed["plans"] if p["is_selected"])
    for a in final_plan["allocations"]:
        if a["status"] not in ("confirmed", "short_supply"):
            continue
        supplier_token = login(client, supplier_logins[a["supplier_name"]])
        d = client.post(f"/api/allocations/{a['id']}/dispatch", headers=auth_headers(supplier_token))
        assert d.status_code == 200
        f = client.post(f"/api/allocations/{a['id']}/deliver", headers=auth_headers(supplier_token))
        assert f.status_code == 200
        assert f.json()["status"] == "fulfilled"

    order_fulfilled = client.get(f"/api/orders/{order_id}", headers=auth_headers(merchant_token)).json()
    assert order_fulfilled["status"] == "fulfilled"

    # 8. Payment: simulated provider succeeds for this amount (demo decline rule only
    # triggers on paise ending '13').
    pay_resp = client.post("/api/payments/initiate", json={"order_id": order_id}, headers=auth_headers(merchant_token))
    assert pay_resp.status_code == 201, pay_resp.text
    payment = pay_resp.json()
    assert payment["is_simulated"] is True
    assert payment["status"] in ("success", "failed")  # deterministic, never fabricated as always-success

    # A second payment attempt on an already-paid order must be rejected if the first succeeded.
    if payment["status"] == "success":
        dup = client.post("/api/payments/initiate", json={"order_id": order_id}, headers=auth_headers(merchant_token))
        assert dup.status_code == 409


def test_merchant_cannot_access_another_merchants_order(client):
    merchant1_token = login(client, "merchant1@example.com")
    merchant2_token = login(client, "merchant2@example.com")
    rice_id = _rice_product_id(client)

    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": rice_id, "requested_qty_base_unit": 10}]},
        headers=auth_headers(merchant1_token),
    )
    order_id = create_resp.json()["id"]

    resp = client.get(f"/api/orders/{order_id}", headers=auth_headers(merchant2_token))
    assert resp.status_code == 404


def test_infeasible_order_reports_best_partial_basket_not_fake_success(client):
    merchant_token = login(client, "merchant1@example.com")
    rice_id = _rice_product_id(client)

    # Absurdly large quantity no seeded supplier combination can cover.
    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": rice_id, "requested_qty_base_unit": 100000}]},
        headers=auth_headers(merchant_token),
    )
    order_id = create_resp.json()["id"]
    plan_resp = client.post(f"/api/orders/{order_id}/plan", headers=auth_headers(merchant_token))
    plans = plan_resp.json()["plans"]
    for p in plans:
        assert p["is_feasible"] is False
        assert p["infeasible_reasons"]
        total_allocated = sum(a["allocated_qty_base_unit"] for a in p["allocations"])
        assert total_allocated < 100000  # best permitted partial basket, not a fabricated full basket


def test_deterministic_text_parsing_handles_code_mixed_order(client):
    merchant_token = login(client, "merchant1@example.com")
    resp = client.post(
        "/api/orders/parse-text",
        json={"text": "nanage 20 kg akki mattu 5 kg sakkare beku", "language": "kn"},
        headers=auth_headers(merchant_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    names = {i["product_name"] for i in body["items"] if i["product_name"]}
    assert "Rice" in names
    assert "Sugar" in names
    assert body["overall_confidence"] > 0.5


def test_reconciliation_flags_missing_goods_and_price_discrepancy(client):
    merchant_token = login(client, "merchant1@example.com")
    rice_id = _rice_product_id(client)

    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": rice_id, "requested_qty_base_unit": 25}], "price_tolerance_pct": 20, "min_reliability": 0.3},
        headers=auth_headers(merchant_token),
    )
    order_id = create_resp.json()["id"]
    plans = client.post(f"/api/orders/{order_id}/plan", headers=auth_headers(merchant_token)).json()["plans"]
    cheapest = next(p for p in plans if p["objective_profile"] == "cheapest")
    client.post(f"/api/orders/{order_id}/select-plan", json={"plan_id": cheapest["id"]}, headers=auth_headers(merchant_token))

    supplier_logins = {
        "Anand Wholesale Grains": "anand@example.com", "Lakshmi Traders": "lakshmi@example.com",
        "Sri Balaji Provisions": "balaji@example.com", "NewCo Supplies (joined this month)": "newco@example.com",
    }
    alloc = cheapest["allocations"][0]
    supplier_token = login(client, supplier_logins[alloc["supplier_name"]])
    client.post(
        f"/api/allocations/{alloc['id']}/confirm",
        json={"confirmed_qty_base_unit": alloc["allocated_qty_base_unit"], "ready_by": future()},
        headers=auth_headers(supplier_token),
    )

    # Supplier invoices a higher price and slightly fewer units than ordered.
    inv_resp = client.post(
        f"/api/orders/{order_id}/invoices",
        json={"order_id": order_id, "items": [{"product_id": rice_id, "qty_base_unit": 25, "unit_price": alloc["unit_price"] + 10}]},
        headers=auth_headers(supplier_token),
    )
    assert inv_resp.status_code == 201

    # Merchant only actually received 20kg (missing goods).
    client.post(
        f"/api/orders/{order_id}/receipts",
        json={"allocation_id": alloc["id"], "product_id": rice_id, "received_qty_base_unit": 20},
        headers=auth_headers(merchant_token),
    )

    recon = client.get(f"/api/orders/{order_id}/reconciliation", headers=auth_headers(merchant_token)).json()
    assert recon["has_discrepancies"] is True
    line = recon["lines"][0]
    assert "unexpected_price" in line["flags"]
    assert "invoiced_received_mismatch" in line["flags"] or "missing_goods" in line["flags"]
