from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.database import SessionLocal
from app.models.catalog import SupplierInventory
from app.models.orders import Allocation
from app.services.optimizer import ItemRequest, OptimizerPolicy, solve_allocation
from tests.conftest import auth_headers, future, login
from tests.test_api_workflow import _rice_product_id
from tests.test_optimizer import make_offer


def new_order(client, **kwargs):
    h = auth_headers(login(client, "merchant1@example.com"))
    body = {"items": [{"product_id": _rice_product_id(client), "requested_qty_base_unit": 100}], "min_reliability": 0.3, "price_tolerance_pct": 20, **kwargs}
    r = client.post('/api/orders', json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json(), h


def planned(client, **kwargs):
    order, h = new_order(client, **kwargs)
    r = client.post(f"/api/orders/{order['id']}/plan", headers=h)
    assert r.status_code == 200, r.text
    plan = next(p for p in r.json()['plans'] if p['objective_profile'] == 'cheapest')
    r = client.post(f"/api/orders/{order['id']}/select-plan", json={'plan_id': plan['id']}, headers=h)
    assert r.status_code == 200, r.text
    return order, h, plan


def supplier_header(client, allocation):
    emails = {'Anand Wholesale Grains': 'anand@example.com', 'Lakshmi Traders': 'lakshmi@example.com', 'Sri Balaji Provisions': 'balaji@example.com', 'NewCo Supplies (joined this month)': 'newco@example.com'}
    return auth_headers(login(client, emails[allocation['supplier_name']]))


def test_admin_registration_denied(client):
    r = client.post('/api/auth/register', json={'email': 'elevate@example.com', 'password': 'not-a-secret', 'full_name': 'Test', 'role': 'admin', 'business_name': 'Test', 'city': 'Test'})
    assert r.status_code == 403


def test_admin_metrics_and_role_boundaries(client):
    assert client.get('/api/admin/metrics').status_code == 401
    assert client.get('/api/admin/metrics', headers=auth_headers(login(client, 'merchant1@example.com'))).status_code == 403
    r = client.get('/api/admin/metrics', headers=auth_headers(login(client, 'admin@example.com')))
    assert r.status_code == 200, r.text
    assert isinstance(r.json()['orders_by_status'], dict)


@pytest.mark.parametrize('field,value', [('budget_cap', -1), ('max_suppliers', 0), ('min_reliability', 1.1), ('price_tolerance_pct', -1)])
def test_invalid_policy(client, field, value):
    h = auth_headers(login(client, 'merchant1@example.com'))
    r = client.post('/api/orders', headers=h, json={'items': [{'product_id': _rice_product_id(client), 'requested_qty_base_unit': 1}], field: value})
    assert r.status_code == 422


def test_unknown_and_duplicate_product(client):
    h = auth_headers(login(client, 'merchant1@example.com'))
    for items in [[{'product_id': 'missing', 'requested_qty_base_unit': 1}], [{'product_id': _rice_product_id(client), 'requested_qty_base_unit': 1}] * 2]:
        assert client.post('/api/orders', headers=h, json={'items': items}).status_code == 422


def test_budget_includes_delivery():
    result = solve_allocation([ItemRequest('i', 'rice', 'Rice', 25, True)], {'rice': [make_offer('o', 's', price=40)]}, {}, OptimizerPolicy('cheapest', 1000, 10, .5, 4))
    assert result.total_cost <= 1000
    assert not result.is_feasible


def test_cheapest_uses_landed_cost():
    result = solve_allocation([ItemRequest('i', 'rice', 'Rice', 25, True)], {'rice': [make_offer('far', 'far', price=39, distance=100), make_offer('near', 'near', price=40, distance=1)]}, {}, OptimizerPolicy('cheapest', None, 10, .5, 4))
    assert result.allocations[0].supplier_id == 'near'


def test_repeated_lines_cannot_double_spend_stock():
    result = solve_allocation([ItemRequest('a', 'rice', 'Rice', 100, True), ItemRequest('b', 'rice', 'Rice', 100, True)], {'rice': [make_offer('o', 's', stock=100)]}, {}, OptimizerPolicy('cheapest', None, 10, .5, 4))
    assert sum(a.allocated_qty_base_unit for a in result.allocations) <= 100
    assert not result.is_feasible


def test_recovery_respects_total_budget_and_supplier_limit(client):
    order, h, p = planned(client, budget_cap=4000, max_suppliers=1)
    a = p['allocations'][0]
    r = client.post(f"/api/allocations/{a['id']}/confirm", json={'confirmed_qty_base_unit': 40, 'ready_by': future()}, headers=supplier_header(client, a))
    assert r.status_code == 200, r.text
    evidence = client.get(f"/api/orders/{order['id']}/evidence", headers=h).json()
    assert evidence['budget_respected'] and evidence['supplier_limit_respected']
    assert evidence['items'][0]['confirmed'] == 40
    assert evidence['items'][0]['uncovered'] == 60
    assert evidence['items'][0]['delivered'] == 0
    assert client.get(f"/api/orders/{order['id']}/evidence", headers=auth_headers(login(client, 'merchant2@example.com'))).status_code == 404


def test_confirmation_retry_and_stock_race(client):
    _, _, p1 = planned(client)
    _, _, p2 = planned(client)
    a1, a2 = p1['allocations'][0], p2['allocations'][0]
    assert a1['supplier_id'] == a2['supplier_id']
    sh = supplier_header(client, a1)
    quantity = a1['allocated_qty_base_unit']
    assert quantity == a2['allocated_qty_base_unit'] and quantity > 0
    with SessionLocal() as db:
        inv_id = db.get(Allocation, a1['id']).inventory_id
        inv = db.get(SupplierInventory, inv_id)
        original_stock = inv.stock_qty_base_unit
        inv.stock_qty_base_unit = quantity
        db.commit()
    def confirm(a):
        return client.post(f"/api/allocations/{a['id']}/confirm", headers=sh, json={'confirmed_qty_base_unit': quantity, 'ready_by': future()})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, [a1, a2]))
        assert sorted(r.status_code for r in results) == [200, 409]
        winner = [a1, a2][next(i for i, r in enumerate(results) if r.status_code == 200)]
        assert confirm(winner).status_code == 409
        with SessionLocal() as db:
            assert db.get(SupplierInventory, inv_id).stock_qty_base_unit == 0
    finally:
        with SessionLocal() as db:
            db.get(SupplierInventory, inv_id).stock_qty_base_unit = original_stock
            db.commit()


def test_superseded_delivery_and_overconfirmation_rejected(client):
    order, h, p = planned(client)
    a = p['allocations'][0]
    sh = supplier_header(client, a)
    path = f"/api/allocations/{a['id']}"
    assert client.post(path+'/confirm', headers=sh, json={'confirmed_qty_base_unit': 101, 'ready_by': future()}).status_code == 422
    assert client.post(path+'/confirm', headers=sh, json={'confirmed_qty_base_unit': 40, 'ready_by': future()}).status_code == 200
    assert client.post(path+'/deliver', headers=sh).status_code == 409
    assert client.post(f"/api/orders/{order['id']}/plan", headers=h).status_code == 409


def test_invoice_cannot_target_unrelated_order(client):
    _, _, p = planned(client)
    other, _ = new_order(client)
    sh = supplier_header(client, p['allocations'][0])
    r = client.post(f"/api/orders/{other['id']}/invoices", headers=sh, json={'order_id': other['id'], 'items': [{'product_id': _rice_product_id(client), 'qty_base_unit': 1, 'unit_price': 1}]})
    assert r.status_code == 403


def test_cross_order_receipt_rejected(client):
    _, _, p = planned(client)
    other, h = new_order(client)
    r = client.post(f"/api/orders/{other['id']}/receipts", headers=h, json={'allocation_id': p['allocations'][0]['id'], 'product_id': _rice_product_id(client), 'received_qty_base_unit': 1})
    assert r.status_code == 422


def test_simulated_callback_cannot_upgrade_failed_payment(client):
    assert client.post('/api/payments/paytm/callback', data={'ORDERID': 'SIM-fake', 'STATUS': 'TXN_SUCCESS'}).status_code == 503


def test_price_ceiling_survives_supplier_failure():
    result = solve_allocation([ItemRequest('i', 'rice', 'Rice', 25, True)], {'rice': [make_offer('o', 's', price=80)]}, {}, OptimizerPolicy('cheapest', None, 10, .5, 4, price_ceiling_by_product={'rice': 44}))
    assert not result.is_feasible
    assert result.allocations == []


def test_empty_supplier_network_is_honest():
    result = solve_allocation([ItemRequest('i', 'rice', 'Rice', 25, True)], {}, {}, OptimizerPolicy('cheapest', None, 10, .5, 4))
    assert not result.is_feasible and result.shortfall_by_item['i'] == 25


def test_confirmed_is_not_delivered_and_reliability_does_not_double_count(client):
    from app.services.reliability import recompute_supplier_reliability
    _, _, plan = planned(client)
    a = plan['allocations'][0]
    with SessionLocal() as db:
        before = recompute_supplier_reliability(db, a['supplier_id']).sample_size
        db.commit()
    r = client.post(f"/api/allocations/{a['id']}/confirm", headers=supplier_header(client, a), json={'confirmed_qty_base_unit': a['allocated_qty_base_unit'], 'ready_by': future()})
    assert r.status_code == 200
    with SessionLocal() as db:
        after = recompute_supplier_reliability(db, a['supplier_id']).sample_size
        assert after == before


def test_stock_failure_rolls_back_confirmation(client):
    _, _, plan = planned(client)
    a = plan['allocations'][0]
    with SessionLocal() as db:
        inv_id = db.get(Allocation, a['id']).inventory_id
        inv = db.get(SupplierInventory, inv_id)
        saved = inv.stock_qty_base_unit
        inv.stock_qty_base_unit = 0
        db.commit()
    try:
        r = client.post(f"/api/allocations/{a['id']}/confirm", headers=supplier_header(client, a), json={'confirmed_qty_base_unit': a['allocated_qty_base_unit'], 'ready_by': future()})
        assert r.status_code == 409
        with SessionLocal() as db:
            assert db.get(Allocation, a['id']).status.value == 'proposed'
    finally:
        with SessionLocal() as db:
            db.get(SupplierInventory, inv_id).stock_qty_base_unit = saved
            db.commit()


def test_low_confidence_basket_can_be_reviewed(client):
    order, h = new_order(client, raw_input_text='unrecognized product gibberish')
    assert order['requires_confirmation']
    assert client.post(f"/api/orders/{order['id']}/plan", headers=h).status_code == 400
    assert client.post(f"/api/orders/{order['id']}/confirm-items", headers=h).status_code == 200
    assert client.post(f"/api/orders/{order['id']}/plan", headers=h).status_code == 200


def test_api_timestamps_carry_utc_offset(client):
    # SQLite drops tzinfo; without an explicit offset browsers parse UTC as local time.
    order, h = new_order(client)
    r = client.get(f"/api/orders/{order['id']}", headers=h)
    assert r.status_code == 200, r.text
    created = datetime.fromisoformat(r.json()['created_at'])
    assert created.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - created) < timedelta(minutes=5)
