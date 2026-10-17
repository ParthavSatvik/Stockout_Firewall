"""Supplier Trust Passport, Promise Ledger view, dispatch board and Commitment Copilot.

All read-only and deterministic. Every rate states its numerator, denominator and
source tables; anything with fewer than MIN_SAMPLE observations is reported as
INSUFFICIENT_HISTORY instead of a number.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median

from sqlalchemy.orm import Session

from app.models.continuity import CommitmentLedgerEntry, SupplyRelay, SupplyRelayInvite
from app.models.core import SupplierProfile
from app.models.ops import Invoice, InvoiceItem, ReceiptRecord
from app.models.orders import Allocation, AllocationStatus, SupplierEvent, SupplierEventType
from app.services.promise import (
    EPS,
    IST,
    STAGES,
    assess_commitment,
    assess_request,
    live_allocations,
    now_utc,
    positions,
    stage_of,
)
from app.services.reliability import NEW_SUPPLIER_PRIOR, get_or_default_reliability

MIN_SAMPLE = 5
DISPATCH_GRACE = timedelta(minutes=30)
DELIVERY_GRACE = timedelta(minutes=60)


def _chain_key(a: Allocation) -> tuple:
    return (a.order_item_id, a.supplier_id, a.inventory_id)


def _chains(db: Session, supplier_id: str) -> tuple[list[Allocation], dict[tuple, list[SupplierEvent]], dict[tuple, list[str]]]:
    """Current line per commitment (selected plan) plus events from every copy of it."""
    current = [a for a in live_allocations(db, supplier_id) if a.status != AllocationStatus.SUPERSEDED]
    every = db.query(Allocation).filter(Allocation.supplier_id == supplier_id).all()
    ids_by_key: dict[tuple, list[str]] = defaultdict(list)
    for a in every:
        ids_by_key[_chain_key(a)].append(a.id)
    events = db.query(SupplierEvent).filter(SupplierEvent.allocation_id.in_([a.id for a in every])).all() if every else []
    key_by_id = {a.id: _chain_key(a) for a in every}
    ev_by_key: dict[tuple, list[SupplierEvent]] = defaultdict(list)
    for e in events:
        ev_by_key[key_by_id[e.allocation_id]].append(e)
    for evs in ev_by_key.values():
        evs.sort(key=lambda e: e.created_at)
    return current, ev_by_key, ids_by_key


def _rate(num: int | float, den: int | float, label: str, numerator: str, denominator: str, higher_is_better: bool = True,
          observations: int | None = None) -> dict:
    """`observations` is the number of independent events behind the rate; it defaults
    to the denominator, but quantity-weighted rates must pass their event count."""
    observations = den if observations is None else observations
    enough = observations >= MIN_SAMPLE
    return {"label": label, "value": round(num / den, 4) if enough and den else None, "numerator": num, "denominator": den,
            "observations": observations,
            "status": "measured" if enough else "INSUFFICIENT_HISTORY", "min_sample": MIN_SAMPLE,
            "definition": f"{numerator} ÷ {denominator}", "higher_is_better": higher_is_better}


def passport(db: Session, supplier: SupplierProfile) -> dict:
    current, ev_by_key, ids_by_key = _chains(db, supplier.id)
    outcomes = defaultdict(int)
    committed_original = delivered_qty = 0.0
    closed_committed = 0.0
    closed_count = 0
    dispatch_obs = dispatch_on_time = delivery_obs = delivery_on_time = 0
    response_minutes: list[float] = []
    quoted_qty = 0.0
    first_seen = last_seen = None

    for a in current:
        key = _chain_key(a)
        evs = ev_by_key.get(key, [])
        types = [e.event_type for e in evs]
        first_seen = min(first_seen, a.created_at) if first_seen else a.created_at
        last_seen = max(last_seen, evs[-1].created_at if evs else a.created_at) if last_seen else (evs[-1].created_at if evs else a.created_at)
        if a.status == AllocationStatus.PROPOSED:
            outcomes["awaiting_decision"] += 1
            continue
        quoted_qty += a.allocated_qty_base_unit
        first_response = next((e for e in evs if e.event_type in (SupplierEventType.CONFIRMED, SupplierEventType.SHORT_SUPPLY, SupplierEventType.REJECTED)), None)
        if first_response is not None:
            response_minutes.append(max(0.0, (first_response.created_at - a.created_at).total_seconds() / 60))
        confirm_ev = next((e for e in evs if e.event_type == SupplierEventType.CONFIRMED), None)
        original = (confirm_ev.payload or {}).get("confirmed_qty_base_unit") if confirm_ev else None
        if SupplierEventType.EXPIRED in types or a.status == AllocationStatus.EXPIRED:
            outcomes["silent_expiry"] += 1
        elif SupplierEventType.DISRUPTED in types:
            outcomes["broken_after_commitment"] += 1
            committed_original += original or a.allocated_qty_base_unit
            closed_committed += original or a.allocated_qty_base_unit
            closed_count += 1
            if a.status == AllocationStatus.FULFILLED:
                delivered_qty += a.confirmed_qty_base_unit or 0
        elif a.status == AllocationStatus.REJECTED or SupplierEventType.REJECTED in types:
            outcomes["declined_upfront"] += 1
        elif SupplierEventType.SHORT_SUPPLY in types:
            outcomes["partial_disclosed_upfront"] += 1
            committed_original += a.confirmed_qty_base_unit or 0
            if a.status == AllocationStatus.FULFILLED:
                closed_committed += a.confirmed_qty_base_unit or 0
                closed_count += 1
                delivered_qty += a.confirmed_qty_base_unit or 0
        else:
            outcomes["accepted_in_full"] += 1
            committed_original += a.confirmed_qty_base_unit or a.allocated_qty_base_unit
            if a.status == AllocationStatus.FULFILLED:
                closed_committed += a.confirmed_qty_base_unit or a.allocated_qty_base_unit
                closed_count += 1
                delivered_qty += a.confirmed_qty_base_unit or a.allocated_qty_base_unit

        ready_by = a.confirmed_ready_by
        dispatched = next((e.created_at for e in evs if e.event_type == SupplierEventType.DISPATCHED), None)
        delivered = next((e.created_at for e in evs if e.event_type == SupplierEventType.DELIVERED), None)
        if ready_by and dispatched:
            dispatch_obs += 1
            dispatch_on_time += dispatched <= ready_by + DISPATCH_GRACE
        if ready_by and delivered:
            delivery_obs += 1
            delivery_on_time += delivered <= ready_by + timedelta(minutes=a.route_duration_minutes or 0) + DELIVERY_GRACE

    decided = sum(v for k, v in outcomes.items() if k != "awaiting_decision")
    commitments = outcomes["accepted_in_full"] + outcomes["partial_disclosed_upfront"] + outcomes["broken_after_commitment"]

    # Price consistency: invoiced unit price vs the price on the commitment.
    alloc_price = {(a.plan.order_id, a.product_id): a.unit_price for a in current}
    inv_lines = (db.query(InvoiceItem, Invoice).join(Invoice, InvoiceItem.invoice_id == Invoice.id)
                 .filter(Invoice.supplier_id == supplier.id).all())
    price_obs = price_ok = 0
    for line, inv in inv_lines:
        quoted = alloc_price.get((inv.order_id, line.product_id))
        if quoted:
            price_obs += 1
            price_ok += abs(line.unit_price - quoted) <= 0.01 * quoted + EPS
    # Quantity discrepancies: merchant-recorded receipts vs what was delivered.
    all_ids = [i for ids in ids_by_key.values() for i in ids]
    receipts = db.query(ReceiptRecord).filter(ReceiptRecord.allocation_id.in_(all_ids)).all() if all_ids else []
    recv_by_key: dict[tuple, float] = defaultdict(float)
    key_by_id = {i: k for k, ids in ids_by_key.items() for i in ids}
    for r in receipts:
        recv_by_key[key_by_id[r.allocation_id]] += r.received_qty_base_unit
    qty_obs = qty_ok = 0
    for a in current:
        key = _chain_key(a)
        if a.status == AllocationStatus.FULFILLED and key in recv_by_key:
            qty_obs += 1
            qty_ok += recv_by_key[key] >= (a.confirmed_qty_base_unit or 0) * 0.995 - EPS

    pos = positions(db, supplier.id)
    fresh_listings = sum(1 for p in pos if p.freshness["status"] in ("fresh", "aging"))
    stat = get_or_default_reliability(db, supplier.id)

    metrics = {
        "fill_rate": _rate(round(delivered_qty, 3), round(closed_committed, 3), "Committed quantity delivered", "delivered qty", "qty committed on closed commitments",
                           observations=closed_count),
        "commitment_kept_rate": _rate(commitments - outcomes["broken_after_commitment"], commitments, "Commitments not broken after acceptance", "commitments kept", "commitments made"),
        "early_disclosure_rate": _rate(outcomes["partial_disclosed_upfront"] + outcomes["declined_upfront"],
                                       outcomes["partial_disclosed_upfront"] + outcomes["declined_upfront"] + outcomes["broken_after_commitment"] + outcomes["silent_expiry"],
                                       "Shortfalls disclosed before committing", "shortfalls disclosed at quote time", "all shortfalls"),
        "silent_expiry_rate": _rate(outcomes["silent_expiry"], decided, "Requests left to expire", "expired without response", "requests decided", higher_is_better=False),
        "on_time_dispatch": _rate(dispatch_on_time, dispatch_obs, "Dispatched by ready-by (+30 min)", "on-time dispatches", "dispatches with a recorded ready-by"),
        "on_time_delivery": _rate(delivery_on_time, delivery_obs, "Delivered by ready-by + travel (+60 min)", "on-time deliveries", "deliveries with a recorded ready-by"),
        "price_consistency": _rate(price_ok, price_obs, "Invoice price matches committed price (±1%)", "matching invoice lines", "invoice lines linked to a commitment"),
        "quantity_accuracy": _rate(qty_ok, qty_obs, "Merchant received what was delivered (±0.5%)", "receipts matching delivery", "delivered commitments with a merchant receipt"),
    }
    strengths, improvements = [], []
    for key, m in metrics.items():
        if m["status"] != "measured":
            continue
        good = m["value"] >= 0.9 if m["higher_is_better"] else m["value"] <= 0.05
        bad = m["value"] < 0.75 if m["higher_is_better"] else m["value"] > 0.15
        if good:
            strengths.append(f"{m['label']}: {m['value']:.0%} ({m['numerator']:g}/{m['denominator']:g})")
        elif bad:
            improvements.append({
                "fill_rate": "Count stock before accepting so commitments match what is physically available.",
                "commitment_kept_rate": "Use a partial commitment or a supply relay at quote time instead of breaking a commitment later.",
                "early_disclosure_rate": "Disclose shortfalls when you respond, not after accepting — early partials are recorded as honest disclosures.",
                "silent_expiry_rate": "Respond to every request, even with a decline; silent expiries are recorded separately.",
                "on_time_dispatch": "Start picking earlier or choose a later ready-by you can meet.",
                "on_time_delivery": "Set ready-by times that include realistic loading and travel time.",
                "price_consistency": "Invoice at the committed price; update your listing before quoting instead.",
                "quantity_accuracy": "Weigh and record packs at dispatch to avoid receipt discrepancies.",
            }[key])
    if pos and fresh_listings < len(pos):
        improvements.append(f"Count stock for {len(pos) - fresh_listings} listing(s): stock not confirmed in 24h is excluded from new merchant plans.")
    if outcomes["partial_disclosed_upfront"]:
        strengths.append(f"{outcomes['partial_disclosed_upfront']} shortfall(s) disclosed honestly at quote time")

    return {
        "supplier_id": supplier.id, "supplier_name": supplier.business_name, "city": supplier.city,
        "sample": {"requests_decided": decided, "commitments": commitments, "awaiting_decision": outcomes["awaiting_decision"],
                   "first_observation": first_seen, "last_observation": last_seen},
        "history_status": "measured" if decided >= MIN_SAMPLE else "INSUFFICIENT_HISTORY",
        "new_supplier_policy": (f"Fewer than {MIN_SAMPLE} decided requests: no rates are published and the planner uses a neutral "
                                f"{NEW_SUPPLIER_PRIOR:.2f} prior labelled low confidence, so new suppliers are not penalised for having no history."),
        "outcomes": dict(outcomes), "quoted_qty": round(quoted_qty, 3), "committed_qty": round(committed_original, 3),
        "delivered_qty": round(delivered_qty, 3), "metrics": metrics,
        "median_response_minutes": round(median(response_minutes), 1) if len(response_minutes) >= MIN_SAMPLE else None,
        "response_sample": len(response_minutes),
        "stock_freshness": {"fresh_listings": fresh_listings, "listings": len(pos)},
        "planner_reliability": {"score": stat.reliability_score, "confidence": stat.confidence, "sample_size": stat.sample_size,
                                "note": "The score the optimizer uses (smoothed fulfilled ÷ terminal commitments). Shown for transparency; the passport does not alter it."},
        "strengths": strengths, "improvements": improvements,
        "provenance": ["supplier_events (confirm, short supply, reject, expiry, disruption, dispatch, delivery)",
                       "allocations on each order's selected plan (one row per commitment)",
                       "invoices / invoice_items (supplier-issued)", "receipt_records (merchant-recorded)",
                       "supplier_inventory stock counts"],
        "method": "Deterministic counts with stated denominators; no composite star rating.",
    }


def _stage_times(db: Session, ids: list[str], evs: list[SupplierEvent]) -> dict:
    times: dict = {}
    for e in evs:
        if e.event_type in (SupplierEventType.CONFIRMED, SupplierEventType.SHORT_SUPPLY) and "reserved" not in times:
            times["reserved"] = e.created_at
        elif e.event_type == SupplierEventType.DISPATCHED:
            times.setdefault("dispatched", e.created_at)
        elif e.event_type == SupplierEventType.DELIVERED:
            times.setdefault("delivered", e.created_at)
    for entry in db.query(CommitmentLedgerEntry).filter(CommitmentLedgerEntry.allocation_id.in_(ids), CommitmentLedgerEntry.action == "stage_changed").all() if ids else []:
        times.setdefault(entry.to_state, entry.created_at)
    return times


def commitment_rows(db: Session, supplier: SupplierProfile, include_closed: bool = True) -> list[dict]:
    current, ev_by_key, ids_by_key = _chains(db, supplier.id)
    pos_by_inv = {p.inventory.id: p for p in positions(db, supplier.id)}
    pp = passport_history_hint(current, ev_by_key)
    all_ids = [i for ids in ids_by_key.values() for i in ids]
    received = defaultdict(float)
    for r in db.query(ReceiptRecord).filter(ReceiptRecord.allocation_id.in_(all_ids)).all() if all_ids else []:
        received[r.allocation_id] += r.received_qty_base_unit
    rows = []
    for a in current:
        stage = stage_of(a)
        if stage is None or (not include_closed and stage == "delivered"):
            continue
        key = _chain_key(a)
        evs = ev_by_key.get(key, [])
        times = _stage_times(db, ids_by_key[key], evs)
        recv = sum(received[i] for i in ids_by_key[key])
        pos = pos_by_inv.get(a.inventory_id)
        risk = assess_commitment(db, supplier, a, pos, pp) if stage not in ("quote", "delivered") else None
        rows.append({
            "allocation_id": a.id, "order_ref": a.plan.order_id[:8], "product_name": a.product.name, "unit": a.product.base_unit,
            "requested_qty": a.allocated_qty_base_unit, "committed_qty": a.confirmed_qty_base_unit, "unit_price": a.unit_price,
            "status": a.status.value, "stage": "reconciled" if stage == "delivered" and recv > 0 else stage,
            "stage_times": times, "ready_by": a.confirmed_ready_by, "quote_valid_until": a.confirmation_expires_at if stage == "quote" else None,
            "received_qty": recv or None, "stock_freshness": pos.freshness if pos else None, "risk": risk,
            "inventory_id": a.inventory_id, "route_duration_minutes": a.route_duration_minutes,
        })
    order = {"quote": 0, "reserved": 1, "picking": 2, "ready": 3, "dispatched": 4, "delivered": 5, "reconciled": 6}
    rows.sort(key=lambda r: (order.get(r["stage"], 9), r["ready_by"] or r["quote_valid_until"] or now_utc() + timedelta(days=365)))
    return rows


def passport_history_hint(current: list[Allocation], ev_by_key: dict) -> dict:
    commitments = broken = 0
    for a in current:
        types = [e.event_type for e in ev_by_key.get(_chain_key(a), [])]
        if SupplierEventType.CONFIRMED in types or SupplierEventType.SHORT_SUPPLY in types:
            commitments += 1
            broken += SupplierEventType.DISRUPTED in types
    return {"broken_rate": broken / commitments if commitments >= MIN_SAMPLE else None}


def promise_ledger(db: Session, supplier: SupplierProfile) -> dict:
    pos = positions(db, supplier.id)
    totals = defaultdict(float)
    for p in pos:
        for k in ("on_hand", "committed", "safety_stock", "free_to_promise", "requested", "in_transit"):
            totals[k] += getattr(p, k)
    return {
        "inventory": [p.as_dict() for p in sorted(pos, key=lambda p: (p.product.name, p.inventory.brand))],
        "commitments": commitment_rows(db, supplier),
        "lifecycle": ["quote", "reserved", "picking", "ready", "dispatched", "delivered", "reconciled"],
        "definitions": {
            "on_hand": "Uncommitted stock + live commitments still in your warehouse (from your last count, minus what has left).",
            "committed": "Quantity you explicitly confirmed on live orders, not yet dispatched.",
            "safety_stock": "Your own buffer. Never offered to merchants; you may dip into it only with a recorded override.",
            "free_to_promise": "max(0, on_hand − committed − safety_stock). The only quantity PromiseGuard lets you promise.",
            "requested_pending": "Open requests awaiting your decision. Not reserved — first confirmed is first reserved.",
            "in_transit": "Dispatched, not yet marked delivered.",
        },
    }


def dispatch_board(db: Session, supplier: SupplierProfile) -> dict:
    rows = [r for r in commitment_rows(db, supplier, include_closed=False) if r["stage"] in STAGES]
    columns = {s: [r for r in rows if r["stage"] == s] for s in ("reserved", "picking", "ready", "dispatched")}
    today = now_utc().astimezone(IST).date()
    load = sum((r["committed_qty"] or 0) for r in rows if r["unit"] == "kg" and r["ready_by"] and r["ready_by"].astimezone(IST).date() == today and r["stage"] != "dispatched")
    return {"columns": columns, "capacity_kg_per_day": supplier.delivery_capacity_kg_per_day, "due_today_kg": round(load, 3),
            "operating_hours": supplier.operating_hours}


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def copilot(db: Session, supplier: SupplierProfile) -> dict:
    now = now_utc()
    items: list[dict] = []
    pos = positions(db, supplier.id)
    current = [a for a in live_allocations(db, supplier.id)]
    partials: list[dict] = []

    for a in current:
        if a.status != AllocationStatus.PROPOSED:
            continue
        guard = assess_request(db, supplier, a)
        hours = (a.confirmation_expires_at - now).total_seconds() / 3600 if a.confirmation_expires_at else None
        sev = "critical" if hours is not None and hours < 1 else "high" if hours is not None and hours < 3 else "medium"
        items.append({
            "kind": "request_awaiting_decision", "severity": sev, "deadline": a.confirmation_expires_at,
            "title": f"Decide on {a.allocated_qty_base_unit:g} {a.product.base_unit} {a.product.name}",
            "why": f"PromiseGuard: {guard['label']} — {guard.get('headline', '')}",
            "consequence": guard.get("consequence_if_ignored") or "The request will expire and be reallocated.",
            "action": {"label": "Review with PromiseGuard", "href": f"/supplier/requests?focus={a.id}"},
            "evidence": [c["detail"] for c in guard["checks"]][:3], "ref": a.id,
        })
        if guard["status"] == "PARTIAL_COMMITMENT_RECOMMENDED":
            partials.append({"allocation_id": a.id, "product_name": a.product.name, "requested": a.allocated_qty_base_unit,
                             "safe_qty": guard["max_feasible_qty"], "revenue_at_safe_qty": guard["revenue_at_max"],
                             "revenue_forgone": guard["revenue_forgone"], "unit": a.product.base_unit})

    invites = (db.query(SupplyRelayInvite).join(SupplyRelay, SupplyRelayInvite.relay_id == SupplyRelay.id)
               .filter(SupplyRelayInvite.partner_supplier_id == supplier.id, SupplyRelay.status == "open",
                       SupplyRelayInvite.status == "invited").all())
    for inv in invites:
        r = inv.relay
        items.append({
            "kind": "relay_invite", "severity": "high", "deadline": r.expires_at,
            "title": f"Relay request: {r.outstanding_qty_base_unit:g} {r.product.base_unit} {r.product.name}",
            "why": f"{r.origin_supplier.business_name} cannot cover this; you are eligible with {(inv.eligibility or {}).get('free_to_promise', 0):g} free to promise.",
            "consequence": "If no partner answers before the window closes the merchant's planner falls back to the open market.",
            "action": {"label": "Quote or decline", "href": f"/supplier/relay?focus={inv.id}"}, "evidence": [], "ref": inv.id,
        })
    for r in db.query(SupplyRelay).filter(SupplyRelay.origin_supplier_id == supplier.id, SupplyRelay.status == "open").all():
        answered = sum(1 for i in r.invites if i.status != "invited")
        items.append({
            "kind": "relay_outgoing", "severity": "medium", "deadline": r.expires_at,
            "title": f"Your relay for {r.outstanding_qty_base_unit:g} {r.product.base_unit} {r.product.name}",
            "why": f"{answered} of {len(r.invites)} partner(s) answered; the merchant approves the final plan.",
            "consequence": "On expiry the merchant's open-market recovery takes over.",
            "action": {"label": "Track relay", "href": "/supplier/relay"}, "evidence": [], "ref": r.id,
        })

    pp = passport_history_hint(current, _chains(db, supplier.id)[1])
    pos_by_inv = {p.inventory.id: p for p in pos}
    at_risk: list[dict] = []
    for a in current:
        stage = stage_of(a)
        if stage in ("reserved", "picking", "ready"):
            risk = assess_commitment(db, supplier, a, pos_by_inv.get(a.inventory_id), pp)
            if risk["level"] in ("at_risk", "critical"):
                at_risk.append({"allocation_id": a.id, "product_name": a.product.name, "qty": a.confirmed_qty_base_unit,
                                "ready_by": a.confirmed_ready_by, "stage": stage, "risk": risk})
                items.append({
                    "kind": "commitment_at_risk", "severity": "critical" if risk["level"] == "critical" else "high",
                    "deadline": a.confirmed_ready_by,
                    "title": f"{a.confirmed_qty_base_unit:g} {a.product.base_unit} {a.product.name} at risk ({stage})",
                    "why": "; ".join(f["detail"] for f in risk["factors"]),
                    "consequence": "A missed commitment is recorded as broken in your passport; disclosing now lets you relay the gap.",
                    "action": {"label": "Open dispatch board", "href": "/supplier/dispatch"},
                    "evidence": [f"{f['factor']} (+{f['points']})" for f in risk["factors"]], "ref": a.id,
                })
        elif stage == "dispatched":
            sent = next((e.created_at for e in a.events if e.event_type == SupplierEventType.DISPATCHED), None)
            if sent and now - sent > timedelta(hours=12):
                items.append({
                    "kind": "delivery_update_missing", "severity": "medium", "deadline": None,
                    "title": f"Confirm delivery of {a.confirmed_qty_base_unit:g} {a.product.base_unit} {a.product.name}",
                    "why": f"Dispatched {(now - sent).total_seconds() / 3600:.0f}h ago with no delivery update.",
                    "consequence": "The merchant's order cannot close and on-time delivery is not recorded.",
                    "action": {"label": "Open dispatch board", "href": "/supplier/dispatch"}, "evidence": [], "ref": a.id,
                })

    low_stock: list[dict] = []
    for p in pos:
        if p.freshness["status"] == "stale":
            items.append({
                "kind": "stale_stock", "severity": "high" if p.requested or p.committed else "medium", "deadline": None,
                "title": f"Count {p.product.name} ({p.inventory.brand})",
                "why": f"Stock last confirmed {p.freshness['age_hours']}h ago.",
                "consequence": "Listings not confirmed in 24h are excluded from new merchant plans.",
                "action": {"label": "Record stock count", "href": f"/supplier/ledger?count={p.inventory.id}"}, "evidence": [], "ref": p.inventory.id,
            })
        if p.drift_qty > EPS:
            items.append({
                "kind": "commitment_drift", "severity": "critical", "deadline": None,
                "title": f"{p.product.name}: counted stock is {p.drift_qty:g} {p.product.base_unit} below commitments",
                "why": f"Last count {p.inventory.reported_on_hand_base_unit:g} vs {p.committed:g} committed.",
                "consequence": "At least one commitment cannot be met as promised.",
                "action": {"label": "Relay or reduce a commitment", "href": "/supplier/dispatch"}, "evidence": [], "ref": p.inventory.id,
            })
        if p.inventory.is_available and (p.free_to_promise + EPS < max(p.inventory.moq_base_unit, 1) or p.requested > p.free_to_promise + EPS):
            low_stock.append({"inventory_id": p.inventory.id, "product_name": p.product.name, "brand": p.inventory.brand,
                              "free_to_promise": p.free_to_promise, "moq": p.inventory.moq_base_unit,
                              "requested_pending": p.requested, "unit": p.product.base_unit})
            if p.requested > p.free_to_promise + EPS:
                items.append({
                    "kind": "oversubscribed", "severity": "high", "deadline": None,
                    "title": f"{p.product.name}: {p.requested:g} requested vs {p.free_to_promise:g} free",
                    "why": "Open requests exceed what you can safely promise.",
                    "consequence": "Accepting all of them would break existing commitments or safety stock.",
                    "action": {"label": "Review requests", "href": "/supplier/requests"}, "evidence": [], "ref": p.inventory.id,
                })

    days: dict = defaultdict(float)
    for a in current:
        if a.status in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY) and stage_of(a) in ("reserved", "picking", "ready") and a.confirmed_ready_by and a.product.base_unit == "kg":
            days[a.confirmed_ready_by.astimezone(IST).date()] += a.confirmed_qty_base_unit or 0
    for day, kg in sorted(days.items()):
        if kg > supplier.delivery_capacity_kg_per_day + EPS:
            items.append({
                "kind": "capacity_overload", "severity": "high", "deadline": None,
                "title": f"{kg:g} kg due {day:%d %b} exceeds {supplier.delivery_capacity_kg_per_day:g} kg/day",
                "why": "Declared daily dispatch capacity is exceeded.", "consequence": "Some ready-by times will slip.",
                "action": {"label": "Open dispatch board", "href": "/supplier/dispatch"}, "evidence": [], "ref": str(day),
            })

    items.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], i["deadline"] or now + timedelta(days=365)))
    best = items[0] if items else None
    return {
        "generated_at": now, "queue": items,
        "answers": {
            "needs_attention_now": [i for i in items if i["severity"] in ("critical", "high")][:5],
            "at_risk_of_missing_dispatch": at_risk,
            "insufficient_stock_for_new_commitments": low_stock,
            "safe_partial_fulfilment": partials,
            "surplus_matches_nearby_demand": [{"invite_id": i.id, "product_name": i.relay.product.name,
                                               "qty": i.relay.outstanding_qty_base_unit, "deadline": i.relay.expires_at,
                                               "distance_to_merchant_km": (i.eligibility or {}).get("distance_to_merchant_km")} for i in invites],
            "best_next_action": ({"title": best["title"], "why": best["why"], "action": best["action"]} if best
                                 else {"title": "Nothing urgent", "why": "No open requests, risks or stale stock.", "action": None}),
        },
        "method": "Deterministic rules over your recorded stock, commitments, deadlines and capacity. No language model decides anything here.",
    }
