"""Supplier Continuity Network: PromiseGuard ledger, Supply Relay Protocol, Trust
Passport and Commitment Copilot. Each test starts from a fresh demo seed so stock
levels are deterministic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.database import SessionLocal
from app.models.catalog import SupplierInventory
from app.models.continuity import CommitmentLedgerEntry, SupplyRelay
from app.seed import seed_data
from tests.conftest import auth_headers, future, login

LOGINS = {
    "Anand Wholesale Grains": "anand@example.com",
    "Lakshmi Traders": "lakshmi@example.com",
    "Sri Balaji Provisions": "balaji@example.com",
    "NewCo Supplies (joined this month)": "newco@example.com",
}


@pytest.fixture(autouse=True)
def fresh_seed():
    seed_data.run()
    yield


def h(client, email):
    return auth_headers(login(client, email))


def product_id(client, name):
    return next(p["id"] for p in client.get("/api/products", headers=h(client, "merchant1@example.com")).json() if p["name"] == name)


def rice_order(client, qty=100, **policy):
    """merchant1 orders rice and approves the cheapest plan (NewCo, 100 kg, at seed)."""
    m = h(client, "merchant1@example.com")
    body = {"items": [{"product_id": product_id(client, "Rice"), "requested_qty_base_unit": qty}],
            "price_tolerance_pct": 20, "min_reliability": 0.3, "budget_cap": 6000, "max_suppliers": 4, **policy}
    order = client.post("/api/orders", json=body, headers=m).json()
    plans = client.post(f"/api/orders/{order['id']}/plan", headers=m).json()["plans"]
    plan = next(p for p in plans if p["objective_profile"] == "cheapest")
    assert client.post(f"/api/orders/{order['id']}/select-plan", json={"plan_id": plan["id"]}, headers=m).status_code == 200
    line = plan["allocations"][0]
    return order["id"], m, line, h(client, LOGINS[line["supplier_name"]])


def anand_atta_request(client):
    sh = h(client, "anand@example.com")
    lines = client.get("/api/suppliers/me/allocations", headers=sh).json()
    return next(a for a in lines if a["status"] == "proposed" and a["product_name"] == "Wheat Atta"), sh


def open_rice_relay(client, commit=40, **policy):
    order_id, m, line, origin = rice_order(client, **policy)
    inv = next(i for i in client.get("/api/suppliers/me/inventory", headers=origin).json() if i["product_name"] == "Rice")
    r = client.post(f"/api/suppliers/me/inventory/{inv['id']}/stock-count", headers=origin,
                    json={"on_hand_base_unit": commit, "reason": "count after damage"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/allocations/{line['id']}/relay", headers=origin,
                    json={"commit_qty_base_unit": commit, "ready_by": future(4), "reason": "Only 40 kg after stock count"})
    assert r.status_code == 201, r.text
    return order_id, m, line, origin, r.json()


def invite_for(client, supplier_name):
    sh = h(client, LOGINS[supplier_name])
    incoming = client.get("/api/relays/mine", headers=sh).json()["incoming"]
    return incoming[0]["invite"]["id"], sh


# 1 ----------------------------------------------------------------------------
def test_free_to_promise_subtracts_commitments_and_safety_stock(client):
    alloc, sh = anand_atta_request(client)
    ledger = client.get("/api/suppliers/me/promise-ledger", headers=sh).json()
    atta = next(i for i in ledger["inventory"] if i["product_name"] == "Wheat Atta")
    assert (atta["on_hand"], atta["committed"], atta["safety_stock"], atta["free_to_promise"]) == (80, 50, 10, 20)
    assert atta["requested_pending"] == 40 and atta["oversubscribed_by"] == 20

    guard = client.get(f"/api/allocations/{alloc['id']}/guard", headers=sh).json()
    assert guard["status"] == "PARTIAL_COMMITMENT_RECOMMENDED"
    assert guard["max_feasible_qty"] == 20 and guard["shortfall_qty"] == 20
    assert guard["revenue_forgone"] == 20 * alloc["unit_price"]
    assert any(c["rule"] == "free_to_promise" and not c["ok"] for c in guard["checks"])


def test_stock_count_does_not_double_count_commitments(client):
    alloc, sh = anand_atta_request(client)
    inv_id = next(i for i in client.get("/api/suppliers/me/inventory", headers=sh).json() if i["product_name"] == "Wheat Atta")["id"]
    # Re-entering the same physical count must not free the 50 kg already promised.
    r = client.post(f"/api/suppliers/me/inventory/{inv_id}/stock-count", headers=sh, json={"on_hand_base_unit": 80})
    assert r.json()["free_to_promise_base_unit"] == 20
    # A count below commitments is drift, not negative stock.
    r = client.post(f"/api/suppliers/me/inventory/{inv_id}/stock-count", headers=sh, json={"on_hand_base_unit": 30})
    assert r.json()["free_to_promise_base_unit"] == 0
    queue = client.get("/api/suppliers/me/copilot", headers=sh).json()["queue"]
    assert any(i["kind"] == "commitment_drift" and i["severity"] == "critical" for i in queue)


# 2 ----------------------------------------------------------------------------
def test_full_acceptance_when_feasible(client):
    order_id, m, line, sh = rice_order(client)
    guard = client.get(f"/api/allocations/{line['id']}/guard", headers=sh).json()
    assert guard["status"] == "SAFE_TO_COMMIT" and guard["max_feasible_qty"] == 100
    night = (datetime.now(UTC) + timedelta(days=1)).replace(hour=21, minute=30)  # 03:00 IST, outside 09:00-20:00
    late = client.get(f"/api/allocations/{line['id']}/guard", headers=sh, params={"ready_by": night.isoformat()}).json()
    assert late["status"] == "DELIVERY_WINDOW_AT_RISK"

    r = client.post(f"/api/allocations/{line['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 100, "ready_by": future(5)})
    assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["fulfillment_stage"] == "reserved"
    rice = next(i for i in client.get("/api/suppliers/me/promise-ledger", headers=sh).json()["inventory"] if i["product_name"] == "Rice")
    assert rice["committed"] == 100 and rice["free_to_promise"] == 0
    assert client.get(f"/api/orders/{order_id}", headers=m).json()["status"] == "confirmed"


def test_ready_by_in_the_past_is_rejected(client):
    _, _, line, sh = rice_order(client)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    r = client.post(f"/api/allocations/{line['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 100, "ready_by": past})
    assert r.status_code == 422


# 3 ----------------------------------------------------------------------------
def test_partial_commitment_and_partner_counteroffer_persist(client):
    order_id, m, line, origin, relay = open_rice_relay(client)
    assert relay["status"] == "open" and relay["outstanding_qty"] == 60 and relay["origin_committed_qty"] == 40
    origin_line = client.get("/api/suppliers/me/allocations", headers=origin).json()
    kept = next(a for a in origin_line if a["id"] == line["id"])
    assert kept["status"] == "short_supply" and kept["confirmed_qty_base_unit"] == 40

    invite_id, bh = invite_for(client, "Sri Balaji Provisions")
    r = client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh,
                    json={"action": "modify", "qty_base_unit": 50, "price_per_base_unit": 39, "ready_by": future(6), "note": "50 at 39"})
    assert r.status_code == 200
    invite = r.json()["invite"]
    assert (invite["status"], invite["offered_qty"], invite["offered_price"]) == ("modified", 50, 39)
    # A counteroffer is a quote, not a reservation: Balaji's free stock is unchanged.
    balaji_rice = next(i for i in client.get("/api/suppliers/me/promise-ledger", headers=bh).json()["inventory"] if i["product_name"] == "Rice")
    assert balaji_rice["committed"] == 0 and balaji_rice["free_to_promise"] == 120
    assert client.get(f"/api/orders/{order_id}", headers=m).json()["status"] == "replanning"


# 4 ----------------------------------------------------------------------------
def test_insufficient_stock_and_safety_stock_override(client):
    alloc, sh = anand_atta_request(client)
    r = client.post(f"/api/allocations/{alloc['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 40, "ready_by": future(5)})
    assert r.status_code == 409 and "20" in r.json()["detail"]
    r = client.post(f"/api/allocations/{alloc['id']}/confirm", headers=sh,
                    json={"confirmed_qty_base_unit": 30, "ready_by": future(5), "override_safety_stock": True})
    assert r.status_code == 422  # an override needs a stated reason
    r = client.post(f"/api/allocations/{alloc['id']}/confirm", headers=sh,
                    json={"confirmed_qty_base_unit": 30, "ready_by": future(5), "override_safety_stock": True, "override_reason": "Regular customer, restock tomorrow"})
    assert r.status_code == 200 and r.json()["status"] == "short_supply"
    with SessionLocal() as db:
        entry = db.query(CommitmentLedgerEntry).filter_by(allocation_id=alloc["id"], action="partial_commitment").one()
        assert entry.payload["safety_stock_override"] is True and "restock" in entry.reason


def test_commitment_conflict_when_everything_is_promised(client):
    alloc, sh = anand_atta_request(client)
    inv_id = next(i for i in client.get("/api/suppliers/me/inventory", headers=sh).json() if i["product_name"] == "Wheat Atta")["id"]
    # Raising safety stock to 30 leaves 80 - 50 committed - 30 safety = 0 free.
    client.post(f"/api/suppliers/me/inventory/{inv_id}/stock-count", headers=sh, json={"on_hand_base_unit": 80, "safety_stock_base_unit": 30})
    guard = client.get(f"/api/allocations/{alloc['id']}/guard", headers=sh).json()
    assert guard["status"] == "COMMITMENT_CONFLICT" and guard["max_feasible_qty"] == 0
    r = client.post(f"/api/allocations/{alloc['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 1, "ready_by": future(5)})
    assert r.status_code == 409


def _inventory_of(db, line):
    from app.models.orders import Allocation
    return db.get(Allocation, line["id"]).inventory_id


# 5 ----------------------------------------------------------------------------
def test_stale_inventory_is_insufficient_data_and_excluded_from_plans(client):
    _, _, line, sh = rice_order(client)
    with SessionLocal() as db:
        inv = db.get(SupplierInventory, _inventory_of(db, line))
        inv.stock_confirmed_at = datetime.now(UTC) - timedelta(hours=30)
        db.commit()
    guard = client.get(f"/api/allocations/{line['id']}/guard", headers=sh).json()
    assert guard["status"] == "INSUFFICIENT_DATA" and guard["max_feasible_qty"] == 0

    # Anand's moong dal is seeded 30h stale: the planner must not offer it.
    m = h(client, "merchant1@example.com")
    order = client.post("/api/orders", headers=m, json={"items": [{"product_id": product_id(client, "Moong Dal"), "requested_qty_base_unit": 25}],
                                                         "min_reliability": 0.3, "price_tolerance_pct": 50}).json()
    plans = client.post(f"/api/orders/{order['id']}/plan", headers=m).json()["plans"]
    assert all(a["supplier_name"] != "Anand Wholesale Grains" for p in plans for a in p["allocations"])
    queue = client.get("/api/suppliers/me/copilot", headers=h(client, "anand@example.com")).json()["queue"]
    assert any(i["kind"] == "stale_stock" and "Moong Dal" in i["title"] for i in queue)


# 6 ----------------------------------------------------------------------------
def test_sku_unit_and_pack_validation(client):
    sh = h(client, "anand@example.com")
    r = client.post("/api/suppliers/me/inventory", headers=sh, json={
        "product_id": product_id(client, "Sugar"), "pack_size": 25, "pack_unit": "litre", "price_per_base_unit": 40, "stock_qty_base_unit": 10})
    assert r.status_code == 422
    alloc, _ = anand_atta_request(client)
    guard = client.get(f"/api/allocations/{alloc['id']}/guard", headers=sh).json()
    assert guard["pack_breakdown"] == {"pack_size": 25.0, "full_packs": 0, "loose_qty": 20.0}

    _, _, _, _, relay = open_rice_relay(client)
    invite_id, bh = invite_for(client, "Sri Balaji Provisions")
    bad = {"action": "modify", "price_per_base_unit": 39, "ready_by": future(6)}
    assert client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh, json={**bad, "qty_base_unit": 12.5}).status_code == 422
    assert client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh, json={**bad, "qty_base_unit": 61}).status_code == 422
    with SessionLocal() as db:  # partner can never quote stock it does not have free
        inv = db.query(SupplierInventory).join(SupplierInventory.supplier).filter_by(business_name="Sri Balaji Provisions").filter(
            SupplierInventory.product_id == product_id(client, "Rice")).one()
        inv.stock_qty_base_unit = 30.0
        db.commit()
    r = client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh, json={**bad, "qty_base_unit": 40})
    assert r.status_code == 409 and "30" in r.json()["detail"]


# 7 ----------------------------------------------------------------------------
def test_passport_rates_have_denominators_and_low_sample_is_insufficient(client):
    lak = client.get("/api/suppliers/me/passport", headers=h(client, "lakshmi@example.com")).json()
    assert lak["history_status"] == "measured"
    on_time = lak["metrics"]["on_time_delivery"]
    assert (on_time["numerator"], on_time["denominator"], on_time["status"]) == (10, 11, "measured")
    assert on_time["value"] == round(10 / 11, 4)
    assert lak["metrics"]["price_consistency"]["value"] == 1.0

    new = client.get("/api/suppliers/me/passport", headers=h(client, "newco@example.com")).json()
    assert new["history_status"] == "INSUFFICIENT_HISTORY"
    assert all(m["value"] is None and m["status"] == "INSUFFICIENT_HISTORY" for m in new["metrics"].values())
    assert "not penalised" in new["new_supplier_policy"]

    anand = client.get("/api/suppliers/me/passport", headers=h(client, "anand@example.com")).json()
    assert anand["outcomes"]["partial_disclosed_upfront"] == 2
    assert any("disclosed honestly" in s for s in anand["strengths"])


# 8 ----------------------------------------------------------------------------
def test_authorization_and_cross_party_isolation(client):
    alloc, _ = anand_atta_request(client)
    other = h(client, "lakshmi@example.com")
    assert client.get(f"/api/allocations/{alloc['id']}/guard", headers=other).status_code == 404
    assert client.post(f"/api/allocations/{alloc['id']}/stage", headers=other, json={"stage": "picking"}).status_code == 404

    order_id, m, _, origin, relay = open_rice_relay(client)
    assert client.get(f"/api/relays/{relay['id']}/candidates", headers=other).status_code == 404  # only the origin
    invite_id, bh = invite_for(client, "Sri Balaji Provisions")
    assert client.post(f"/api/relays/invites/{invite_id}/respond", headers=other, json={"action": "decline"}).status_code == 404
    assert client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=bh).status_code == 403
    m2 = h(client, "merchant2@example.com")
    assert client.get(f"/api/orders/{order_id}/relays", headers=m2).status_code == 404
    assert client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=m2).status_code == 404

    partner_view = client.get("/api/relays/mine", headers=bh).json()["incoming"][0]
    assert "invites" not in partner_view and "order_id" not in partner_view
    assert "withheld" in partner_view["merchant"]


# 9 ----------------------------------------------------------------------------
def test_concurrent_acceptance_reserves_stock_once(client):
    _, _, line, sh = rice_order(client)

    def confirm():
        return client.post(f"/api/allocations/{line['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 100, "ready_by": future(5)}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(lambda _: confirm(), range(2)))
    assert codes == [200, 409]
    rice = next(i for i in client.get("/api/suppliers/me/promise-ledger", headers=sh).json()["inventory"] if i["product_name"] == "Rice")
    assert rice["committed"] == 100 and rice["uncommitted"] == 0


def test_duplicate_stage_events_are_idempotent_and_forward_only(client):
    _, _, line, sh = rice_order(client)
    client.post(f"/api/allocations/{line['id']}/confirm", headers=sh, json={"confirmed_qty_base_unit": 100, "ready_by": future(5)})
    for _ in range(2):
        assert client.post(f"/api/allocations/{line['id']}/stage", headers=sh, json={"stage": "picking"}).status_code == 200
    with SessionLocal() as db:
        assert db.query(CommitmentLedgerEntry).filter_by(allocation_id=line["id"], action="stage_changed").count() == 1
    assert client.post(f"/api/allocations/{line['id']}/stage", headers=sh, json={"stage": "ready"}).json()["fulfillment_stage"] == "ready"
    assert client.post(f"/api/allocations/{line['id']}/stage", headers=sh, json={"stage": "picking"}).status_code == 409
    for _ in range(2):
        assert client.post(f"/api/allocations/{line['id']}/dispatch", headers=sh).status_code == 200
    assert client.post(f"/api/allocations/{line['id']}/deliver", headers=sh).json()["status"] == "fulfilled"
    board = client.get("/api/suppliers/me/dispatch-board", headers=sh).json()
    assert all(r["allocation_id"] != line["id"] for col in board["columns"].values() for r in col)


def test_double_approval_is_refused(client):
    order_id, m, _, _, relay = open_rice_relay(client)
    invite_id, bh = invite_for(client, "Sri Balaji Provisions")
    client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh, json={"action": "accept", "ready_by": future(6)})
    first = client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=m)
    second = client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=m)
    assert (first.status_code, second.status_code) == (200, 409)
    balaji = next(i for i in client.get("/api/suppliers/me/promise-ledger", headers=bh).json()["inventory"] if i["product_name"] == "Rice")
    assert balaji["committed"] == 60  # reserved exactly once


# 10 + 12 ----------------------------------------------------------------------
def test_relay_recovers_100_40_60_with_recalculated_cost_and_audit_trail(client):
    order_id, m, line, origin, relay = open_rice_relay(client)
    assert {i["supplier_name"] for i in relay["invites"]} == {"Anand Wholesale Grains", "Sri Balaji Provisions", "Lakshmi Traders"}
    for name, body in [("Sri Balaji Provisions", {"action": "modify", "qty_base_unit": 60, "price_per_base_unit": 39, "ready_by": future(5)}),
                       ("Lakshmi Traders", {"action": "accept", "ready_by": future(6)}),
                       ("Anand Wholesale Grains", {"action": "decline", "note": "dispatch van busy"})]:
        invite_id, ph = invite_for(client, name)
        assert client.post(f"/api/relays/invites/{invite_id}/respond", headers=ph, json=body).status_code == 200

    view = client.get(f"/api/orders/{order_id}/relays", headers=m).json()[0]
    pv = view["preview"]
    assert pv["covered"] == 60 and pv["uncovered"] == 0
    assert [(ln["supplier_name"], ln["qty"], ln["unit_price"]) for ln in pv["lines"]] == [("Sri Balaji Provisions", 60, 39)]
    before = pv["current_landed_cost"]
    assert before == pytest.approx(40 * 36 + line["route_cost"], abs=0.01)

    r = client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=m)
    assert r.status_code == 200 and r.json()["order_status"] == "confirmed"
    order = client.get(f"/api/orders/{order_id}", headers=m).json()
    plan = next(p for p in order["plans"] if p["is_selected"])
    assert plan["replan_reason"] == "supply_relay"
    lines = {a["supplier_name"]: a for a in plan["allocations"]}
    assert lines["NewCo Supplies (joined this month)"]["confirmed_qty_base_unit"] == 40
    assert lines["Sri Balaji Provisions"]["status"] == "confirmed" and lines["Sri Balaji Provisions"]["unit_price"] == 39
    assert plan["total_cost"] == pytest.approx(pv["new_landed_cost"], abs=0.01)
    assert plan["total_cost"] <= 6000
    ev = client.get(f"/api/orders/{order_id}/evidence", headers=m).json()["items"][0]
    assert (ev["confirmed"], ev["uncovered"], ev["no_recovery_baseline"]) == (100, 0, 40)

    trail = client.get(f"/api/orders/{order_id}/commitment-ledger", headers=m).json()
    actions = [e["action"] for e in trail]
    for expected in ("partial_commitment", "relay_opened", "relay_modified", "relay_accepted", "relay_declined",
                     "relay_approved", "relay_stock_reserved"):
        assert expected in actions
    approved = next(e for e in trail if e["action"] == "relay_approved")
    assert (approved["from_state"], approved["to_state"], approved["actor_role"]) == ("open", "approved", "merchant")
    lak = client.get("/api/relays/mine", headers=h(client, "lakshmi@example.com")).json()["incoming"][0]
    assert lak["invite"]["status"] == "not_selected"


# 11 ---------------------------------------------------------------------------
def test_unrecoverable_shortage_reports_uncovered_quantity(client):
    order_id, m, _, _, relay = open_rice_relay(client, max_suppliers=1)
    invite_id, bh = invite_for(client, "Sri Balaji Provisions")
    client.post(f"/api/relays/invites/{invite_id}/respond", headers=bh, json={"action": "accept", "ready_by": future(6)})
    pv = client.get(f"/api/orders/{order_id}/relays", headers=m).json()[0]["preview"]
    assert pv["uncovered"] == 60 and not pv["lines"]  # supplier limit 1 is already used by the origin
    assert client.post(f"/api/orders/{order_id}/relays/{relay['id']}/approve", headers=m).status_code == 409

    r = client.post(f"/api/orders/{order_id}/relays/{relay['id']}/decline", headers=m, json={"note": "try open market"})
    assert r.status_code == 200
    order = client.get(f"/api/orders/{order_id}", headers=m).json()
    assert order["status"] not in ("confirmed", "fulfilled")
    ev = client.get(f"/api/orders/{order_id}/evidence", headers=m).json()["items"][0]
    assert ev["confirmed"] == 40 and ev["uncovered"] == 60


def test_no_eligible_partner_falls_back_immediately(client):
    order_id, m, line, origin = rice_order(client)
    with SessionLocal() as db:  # every other rice listing is stale
        for inv in db.query(SupplierInventory).filter(SupplierInventory.product_id == product_id(client, "Rice"),
                                                       SupplierInventory.id != _inventory_of(db, line)).all():
            inv.stock_confirmed_at = datetime.now(UTC) - timedelta(days=3)
        db.commit()
    r = client.post(f"/api/allocations/{line['id']}/relay", headers=origin,
                    json={"commit_qty_base_unit": 40, "ready_by": future(4), "reason": "short"})
    assert r.status_code == 201 and r.json()["status"] == "fallback"
    plan = next(p for p in client.get(f"/api/orders/{order_id}", headers=m).json()["plans"] if p["is_selected"])
    assert plan["replan_reason"] == "short_supply"


def test_expired_relay_hands_over_to_open_market_recovery(client):
    order_id, m, _, _, relay = open_rice_relay(client)
    with SessionLocal() as db:
        db.get(SupplyRelay, relay["id"]).expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    order = client.get(f"/api/orders/{order_id}", headers=m).json()
    plan = next(p for p in order["plans"] if p["is_selected"])
    assert plan["replan_reason"] == "short_supply"
    relays = client.get(f"/api/orders/{order_id}/relays", headers=m).json()
    assert relays[0]["status"] == "expired"


def test_copilot_answers_are_backed_by_records(client):
    alloc, sh = anand_atta_request(client)
    cp = client.get("/api/suppliers/me/copilot", headers=sh).json()
    partial = cp["answers"]["safe_partial_fulfilment"]
    assert partial == [{"allocation_id": alloc["id"], "product_name": "Wheat Atta", "requested": 40, "safe_qty": 20,
                        "revenue_at_safe_qty": 20 * alloc["unit_price"], "revenue_forgone": 20 * alloc["unit_price"], "unit": "kg"}]
    assert any(s["product_name"] == "Wheat Atta" for s in cp["answers"]["insufficient_stock_for_new_commitments"])
    assert cp["answers"]["best_next_action"]["action"] is not None


def test_quantity_weighted_rate_needs_enough_commitments_not_enough_kilograms(client):
    # Balaji has 3 closed commitments totalling 60 kg: 60 is not a sample size.
    fill = client.get("/api/suppliers/me/passport", headers=h(client, "balaji@example.com")).json()["metrics"]["fill_rate"]
    assert (fill["denominator"], fill["observations"], fill["status"], fill["value"]) == (60, 3, "INSUFFICIENT_HISTORY", None)
