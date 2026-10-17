"""Supply Relay Protocol: a supplier that cannot fully honour a request hands the
exact outstanding quantity to eligible partner wholesalers instead of leaving the
merchant to start again.

  1. origin commits what it can (atomically reserved) and opens a relay for the rest
  2. eligibility is computed from recorded data; eligible partners are invited
  3. partners accept / modify / decline -- a response is a conditional quote, not stock
  4. the merchant sees a preview built by the same optimizer under the same policy
  5. merchant approval persists the plan through replan_after_event and reserves each
     selected partner's stock atomically; anything that cannot be reserved stays a
     normal pending request. Decline, expiry or no eligible partner falls back to the
     standard open-market recovery, so the merchant is never left waiting.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.catalog import SupplierInventory
from app.models.continuity import SupplyRelay, SupplyRelayInvite
from app.models.core import MerchantProfile, SupplierProfile, User
from app.models.ops import Notification
from app.models.orders import (
    Allocation,
    AllocationPlan,
    AllocationStatus,
    Order,
    OrderItem,
    SupplierEvent,
    SupplierEventType,
)
from app.services import optimizer
from app.services.geo import estimate_distance_km, estimate_duration_minutes
from app.services.planning import (
    _all_excluded_offer_ids,
    build_recovery_problem,
    get_selected_plan,
    initial_price_ceilings,
    open_relays,
    outstanding_by_item,
    recompute_plan_totals,
    replan_after_event,
    sync_order_status,
)
from app.services.promise import EPS, log, now_utc, position_for, reserve_stock
from app.services.reliability import get_or_default_reliability, recompute_supplier_reliability

RESPONDABLE = ("invited", "accepted", "modified")
QUOTED = ("accepted", "modified")


def _notify(db: Session, user_id: str, title: str, message: str, order_id: str | None = None) -> None:
    db.add(Notification(user_id=user_id, type="supply_relay", title=title[:200], message=message[:500], related_order_id=order_id))


def candidates(db: Session, order: Order, product_id: str, origin_supplier_id: str, outstanding: float,
               price_ceiling: float | None, required_brand: str | None) -> list[dict]:
    """Every other wholesaler listing this product, with the recorded evidence that makes
    it eligible or the specific reasons it is not."""
    merchant = db.get(MerchantProfile, order.merchant_id)
    failed = _all_excluded_offer_ids(db, order)
    rows = (db.query(SupplierInventory).join(SupplierProfile, SupplierInventory.supplier_id == SupplierProfile.id)
            .filter(SupplierInventory.product_id == product_id, SupplierProfile.is_active.is_(True),
                    SupplierInventory.supplier_id != origin_supplier_id).all())
    out = []
    for inv in rows:
        pos = position_for(db, inv)
        stat = get_or_default_reliability(db, inv.supplier_id)
        distance = estimate_distance_km(merchant.latitude, merchant.longitude, inv.supplier.latitude, inv.supplier.longitude)
        needed_min = min(inv.moq_base_unit or 0.0, outstanding)
        reasons = []
        if not inv.is_available:
            reasons.append("listing paused by the supplier")
        if inv.pack_unit != inv.product.base_unit:
            reasons.append(f"unit {inv.pack_unit} does not match {inv.product.base_unit}")
        if required_brand and inv.brand != required_brand:
            reasons.append(f"brand {inv.brand} differs and the merchant did not allow substitution")
        if pos.freshness["status"] in ("stale", "unknown"):
            reasons.append(f"stock not confirmed in the last 24h ({pos.freshness['age_hours']}h)")
        if inv.id in failed:
            reasons.append("this offer already failed on this order")
        if pos.free_to_promise <= EPS or pos.free_to_promise + EPS < needed_min:
            reasons.append(f"free to promise {pos.free_to_promise:g} below the minimum useful quantity {needed_min:g}")
        if price_ceiling is not None and inv.price_per_base_unit > price_ceiling + EPS:
            reasons.append(f"listed ₹{inv.price_per_base_unit:g} above the merchant's ceiling ₹{price_ceiling:.2f}")
        if stat.reliability_score + EPS < order.min_reliability:
            reasons.append(f"reliability {stat.reliability_score:.2f} below the merchant's minimum {order.min_reliability:.2f}")
        out.append({
            "supplier_id": inv.supplier_id, "supplier_name": inv.supplier.business_name, "inventory_id": inv.id,
            "brand": inv.brand, "free_to_promise": round(pos.free_to_promise, 3), "moq": inv.moq_base_unit,
            "listed_price": inv.price_per_base_unit, "reliability_score": stat.reliability_score,
            "reliability_confidence": stat.confidence, "reliability_sample_size": stat.sample_size,
            "distance_to_merchant_km": round(distance, 1), "estimated_travel_minutes": round(estimate_duration_minutes(distance)),
            "stock_freshness": pos.freshness["status"], "eligible": not reasons, "reasons": reasons,
        })
    out.sort(key=lambda c: (not c["eligible"], c["listed_price"], c["distance_to_merchant_km"]))
    return out


def open_relay(db: Session, user: User, supplier: SupplierProfile, alloc: Allocation, order: Order,
               commit_qty: float, ready_by: datetime | None, reason: str, window_minutes: int) -> SupplyRelay:
    """Origin supplier keeps `commit_qty` and asks the network for the rest."""
    if alloc.inventory_id is None:
        raise HTTPException(409, "This request predates inventory references; reject it instead")
    if open_relays(db, order):
        raise HTTPException(409, "A relay is already collecting partner responses for this order")
    plan = db.get(AllocationPlan, alloc.plan_id)
    item = db.get(OrderItem, alloc.order_item_id)
    inv = db.get(SupplierInventory, alloc.inventory_id)
    previous = alloc.status.value
    now = now_utc()

    if alloc.status == AllocationStatus.PROPOSED:
        if commit_qty >= alloc.allocated_qty_base_unit - EPS:
            raise HTTPException(422, "You can supply the full quantity; accept the request instead of opening a relay")
        if commit_qty > EPS:
            if ready_by is None or ready_by <= now:
                raise HTTPException(422, "A future ready-by time is required for the quantity you commit")
            if not reserve_stock(db, inv.id, commit_qty):
                pos = position_for(db, inv)
                raise HTTPException(409, f"Only {pos.free_to_promise:g} {inv.product.base_unit} is free to promise")
            alloc.status = AllocationStatus.SHORT_SUPPLY
            alloc.fulfillment_stage = "reserved"
            alloc.confirmed_ready_by = ready_by
            event = SupplierEventType.SHORT_SUPPLY
        else:
            alloc.status = AllocationStatus.REJECTED
            event = SupplierEventType.REJECTED
        alloc.confirmed_qty_base_unit = commit_qty
        disclosure = "at_quote"
    elif alloc.status in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY) and alloc.fulfillment_stage in (None, "reserved", "picking", "ready"):
        held = alloc.confirmed_qty_base_unit or alloc.allocated_qty_base_unit
        if commit_qty >= held - EPS:
            raise HTTPException(422, "Relay quantity must be below your current commitment")
        alloc.status = AllocationStatus.SHORT_SUPPLY
        alloc.confirmed_qty_base_unit = commit_qty
        event = SupplierEventType.DISRUPTED
        disclosure = "after_commitment"
    else:
        raise HTTPException(409, f"A relay cannot be opened on a {alloc.status.value} line at stage {alloc.fulfillment_stage}")

    db.add(SupplierEvent(allocation_id=alloc.id, event_type=event, triggered_replan=False,
                         payload={"confirmed_qty_base_unit": commit_qty, "reason": reason, "supply_relay": True, "disclosure": disclosure}))
    log(db, "partial_commitment" if commit_qty > EPS else "declined_with_relay", actor_user_id=user.id, actor_role="supplier",
        supplier_id=supplier.id, order_id=order.id, allocation_id=alloc.id, inventory_id=inv.id,
        from_state=previous, to_state=alloc.status.value, qty=commit_qty, reason=reason,
        payload={"requested": alloc.allocated_qty_base_unit, "disclosure": disclosure})
    db.flush()
    db.refresh(plan)
    recompute_plan_totals(db, plan)

    outstanding = outstanding_by_item(order, plan)[item.id]
    if outstanding <= EPS:
        raise HTTPException(422, "Nothing is outstanding on this order line")
    ceiling = initial_price_ceilings(order).get(item.product_id)
    relay = SupplyRelay(
        order_id=order.id, order_item_id=item.id, product_id=item.product_id, origin_supplier_id=supplier.id,
        origin_allocation_id=alloc.id, source_plan_id=plan.id, outstanding_qty_base_unit=outstanding,
        origin_committed_qty_base_unit=commit_qty, price_ceiling_per_base_unit=ceiling,
        required_brand=None if item.substitution_allowed else inv.brand,
        needed_by=ready_by or alloc.confirmed_ready_by or now + timedelta(hours=24),
        expires_at=now + timedelta(minutes=window_minutes), reason=reason,
    )
    db.add(relay)
    db.flush()
    log(db, "relay_opened", actor_user_id=user.id, actor_role="supplier", supplier_id=supplier.id, order_id=order.id,
        allocation_id=alloc.id, relay_id=relay.id, to_state="open", qty=outstanding, reason=reason,
        payload={"price_ceiling": ceiling, "required_brand": relay.required_brand, "expires_at": relay.expires_at.isoformat()})

    eligible = [c for c in candidates(db, order, item.product_id, supplier.id, outstanding, ceiling, relay.required_brand) if c["eligible"]]
    merchant_user = db.get(MerchantProfile, order.merchant_id).user_id
    if not eligible:
        relay.status = "fallback"
        relay.resolved_at = now
        relay.resolution_note = "No eligible partner wholesaler; standard open-market recovery ran instead"
        log(db, "relay_fallback", supplier_id=supplier.id, order_id=order.id, relay_id=relay.id,
            from_state="open", to_state="fallback", reason=relay.resolution_note)
        db.flush()
        replan_after_event(db, order, alloc, reason="short_supply" if commit_qty > EPS else "rejected")
    else:
        for c in eligible:
            partner_inv = db.get(SupplierInventory, c["inventory_id"])
            db.add(SupplyRelayInvite(relay_id=relay.id, partner_supplier_id=c["supplier_id"], inventory_id=partner_inv.id, eligibility=c))
            log(db, "relay_invite_sent", supplier_id=c["supplier_id"], order_id=order.id, relay_id=relay.id,
                to_state="invited", qty=outstanding, visible_to_merchant=True,
                reason=f"Eligible: {c['free_to_promise']:g} free, ₹{c['listed_price']:g}, {c['distance_to_merchant_km']} km from merchant")
            _notify(db, partner_inv.supplier.user_id, "Supply relay request",
                    f"{outstanding:g} {inv.product.base_unit} of {inv.product.name} needed; respond before {relay.expires_at:%H:%M} UTC")
        _notify(db, merchant_user, "Supplier opened a supply relay",
                f"{supplier.business_name} committed {commit_qty:g} and invited {len(eligible)} partner(s) for the remaining {outstanding:g}", order.id)
        sync_order_status(db, order)
    recompute_supplier_reliability(db, supplier.id)
    db.flush()
    return relay


def respond(db: Session, user: User, partner: SupplierProfile, invite: SupplyRelayInvite, action: str,
            qty: float | None, price: float | None, ready_by: datetime | None, note: str) -> SupplyRelayInvite:
    relay = invite.relay
    if relay.status != "open" or relay.expires_at <= now_utc():
        raise HTTPException(409, f"This relay is {relay.status if relay.status != 'open' else 'past its response window'}")
    if invite.status not in RESPONDABLE:
        raise HTTPException(409, f"Invite is already {invite.status}")
    previous = invite.status
    inv = db.get(SupplierInventory, invite.inventory_id)
    if action == "decline":
        invite.status = "declined"
        invite.offered_qty_base_unit = None
    else:
        if action == "accept":
            qty, price = relay.outstanding_qty_base_unit, inv.price_per_base_unit
        if qty is None or price is None or ready_by is None:
            raise HTTPException(422, "Quantity, price and ready-by time are required")
        if abs(qty - round(qty)) > EPS:
            raise HTTPException(422, f"Quote whole {inv.product.base_unit} quantities")
        if qty > relay.outstanding_qty_base_unit + EPS:
            raise HTTPException(422, f"Only {relay.outstanding_qty_base_unit:g} is outstanding")
        if ready_by <= now_utc():
            raise HTTPException(422, "Ready-by must be in the future")
        pos = position_for(db, inv)
        if qty > pos.free_to_promise + EPS:
            raise HTTPException(409, f"You have {pos.free_to_promise:g} {inv.product.base_unit} free to promise; quote at most that")
        invite.status = "accepted" if action == "accept" else "modified"
        invite.offered_qty_base_unit = qty
        invite.offered_price_per_base_unit = price
        invite.offered_ready_by = ready_by
    invite.note = note[:300]
    invite.responded_at = now_utc()
    log(db, f"relay_{invite.status}", actor_user_id=user.id, actor_role="supplier", supplier_id=partner.id,
        order_id=relay.order_id, relay_id=relay.id, inventory_id=inv.id, from_state=previous, to_state=invite.status,
        qty=invite.offered_qty_base_unit, reason=note,
        payload={"price": invite.offered_price_per_base_unit,
                 "ready_by": invite.offered_ready_by.isoformat() if invite.offered_ready_by else None,
                 "within_price_policy": relay.price_ceiling_per_base_unit is None or (price or 0) <= relay.price_ceiling_per_base_unit + EPS})
    _notify(db, relay.origin_supplier.user_id, f"Relay partner {invite.status}", f"{partner.business_name} {invite.status} your relay")
    db.flush()
    return invite


def _quote_offers(db: Session, relay: SupplyRelay, order: Order) -> tuple[list[optimizer.OfferCandidate], list[dict]]:
    merchant = db.get(MerchantProfile, order.merchant_id)
    offers, excluded = [], []
    for inv_row in relay.invites:
        if inv_row.status not in QUOTED:
            continue
        inv = db.get(SupplierInventory, inv_row.inventory_id)
        name = inv_row.partner_supplier.business_name
        price = inv_row.offered_price_per_base_unit
        usable = min(inv_row.offered_qty_base_unit, position_for(db, inv).free_to_promise)
        stat = get_or_default_reliability(db, inv_row.partner_supplier_id)
        if relay.price_ceiling_per_base_unit is not None and price > relay.price_ceiling_per_base_unit + EPS:
            excluded.append({"supplier_name": name, "reason": f"quoted ₹{price:g} exceeds the merchant's approved ceiling ₹{relay.price_ceiling_per_base_unit:.2f}"})
            continue
        if usable <= EPS:
            excluded.append({"supplier_name": name, "reason": "partner no longer has free stock for this quote"})
            continue
        if stat.reliability_score + EPS < order.min_reliability:
            excluded.append({"supplier_name": name, "reason": "reliability now below the merchant's minimum"})
            continue
        offers.append(optimizer.OfferCandidate(
            offer_id=inv.id, supplier_id=inv.supplier_id, supplier_name=name, product_id=relay.product_id,
            pack_size_base_unit=1.0,  # partners quote exact whole units; their listing MOQ is waived by the quote
            price_per_base_unit=price, stock_qty_base_unit=float(int(usable + EPS)), moq_base_unit=0.0,
            reliability_score=stat.reliability_score, reliability_confidence=stat.confidence,
            distance_km=estimate_distance_km(merchant.latitude, merchant.longitude, inv.supplier.latitude, inv.supplier.longitude),
        ))
    return offers, excluded


def preview(db: Session, relay: SupplyRelay) -> dict:
    """Read-only: what approving now would produce, under the merchant's policy."""
    order = db.get(Order, relay.order_id)
    plan = get_selected_plan(order)
    if plan is None or plan.id != relay.source_plan_id:
        return {"available": False, "reason": "The order's plan changed after the relay opened"}
    outstanding = outstanding_by_item(order, plan)
    offers, excluded = _quote_offers(db, relay, order)
    if not offers:
        return {"available": False, "reason": "No partner quote is usable yet", "excluded_quotes": excluded,
                "outstanding": outstanding.get(relay.order_item_id, 0.0)}
    items, offers_by_product, capacities, policy = build_recovery_problem(
        db, order, plan, outstanding, set(), {relay.product_id: offers})
    result = optimizer.solve_allocation(items, offers_by_product, capacities, policy)
    names = {o.offer_id: o.supplier_name for o in offers}
    by_offer = {i.inventory_id: i for i in relay.invites}
    lines = [{
        "supplier_name": names[line.offer_id], "qty": line.allocated_qty_base_unit, "unit_price": line.unit_price,
        "line_cost": round(line.allocated_qty_base_unit * line.unit_price, 2), "distance_km": round(line.distance_km, 1),
        "ready_by": by_offer[line.offer_id].offered_ready_by,
    } for line in result.allocations]
    covered = sum(line["qty"] for line in lines)
    return {
        "available": True, "is_feasible": result.is_feasible, "lines": lines,
        "outstanding": outstanding.get(relay.order_item_id, 0.0), "covered": round(covered, 3),
        "uncovered": round(max(0.0, outstanding.get(relay.order_item_id, 0.0) - covered), 3),
        "added_product_cost": result.total_product_cost, "added_delivery_cost": result.total_delivery_cost,
        "current_landed_cost": plan.total_cost, "new_landed_cost": round(plan.total_cost + result.total_cost, 2),
        "budget_cap": order.budget_cap, "budget_remaining_for_recovery": policy.budget_cap,
        "price_ceiling": round(relay.price_ceiling_per_base_unit, 2) if relay.price_ceiling_per_base_unit is not None else None, "max_suppliers": order.max_suppliers,
        "infeasible_reasons": result.infeasible_reasons, "excluded_quotes": excluded,
        "policy_note": "Same optimizer and limits as automatic recovery: remaining budget, original price ceiling, minimum reliability, supplier limit.",
    }


def _close(db: Session, relay: SupplyRelay, status: str, note: str, actor: User | None = None, role: str = "system") -> bool:
    """Compare-and-set so a relay is resolved exactly once even under retries."""
    changed = db.execute(update(SupplyRelay).where(SupplyRelay.id == relay.id, SupplyRelay.status == "open")
                         .values(status=status, resolution_note=note[:300], resolved_at=now_utc()))
    db.refresh(relay)
    if changed.rowcount != 1:
        return False
    log(db, f"relay_{status}", actor_user_id=actor.id if actor else None, actor_role=role, supplier_id=relay.origin_supplier_id,
        order_id=relay.order_id, relay_id=relay.id, from_state="open", to_state=status, reason=note)
    return True


def approve(db: Session, user: User, relay: SupplyRelay) -> AllocationPlan:
    order = db.get(Order, relay.order_id)
    expire_if_due(db, relay)
    if relay.status != "open":
        raise HTTPException(409, f"Relay is {relay.status}")
    pv = preview(db, relay)
    if not pv["available"] or not pv["lines"]:
        raise HTTPException(409, pv.get("reason") or "No feasible relay plan; decline to run open-market recovery")
    offers, _ = _quote_offers(db, relay, order)
    origin = db.get(Allocation, relay.origin_allocation_id)
    if not _close(db, relay, "approved", "Merchant approved the relay plan", user, "merchant"):
        raise HTTPException(409, "Relay was already resolved")
    new_plan = replan_after_event(db, order, origin, reason="supply_relay", offers_override={relay.product_id: offers})
    new_plan.explanation = {**(new_plan.explanation or {}), "supply_relay_id": relay.id}
    relay.resolved_plan_id = new_plan.id

    invites = {i.inventory_id: i for i in relay.invites}
    selected = set()
    for a in new_plan.allocations:
        invite = invites.get(a.inventory_id)
        if a.status != AllocationStatus.PROPOSED or invite is None:
            continue
        selected.add(invite.id)
        # The partner's quote was an explicit commitment conditional on this approval.
        if reserve_stock(db, a.inventory_id, a.allocated_qty_base_unit):
            a.status = AllocationStatus.CONFIRMED
            a.confirmed_qty_base_unit = a.allocated_qty_base_unit
            a.confirmed_ready_by = invite.offered_ready_by
            a.fulfillment_stage = "reserved"
            invite.status = "reserved"
            db.add(SupplierEvent(allocation_id=a.id, event_type=SupplierEventType.CONFIRMED,
                                 payload={"confirmed_qty_base_unit": a.allocated_qty_base_unit, "supply_relay": relay.id}))
            log(db, "relay_stock_reserved", supplier_id=a.supplier_id, order_id=order.id, allocation_id=a.id,
                inventory_id=a.inventory_id, relay_id=relay.id, from_state="proposed", to_state="confirmed",
                qty=a.allocated_qty_base_unit, reason="Reserved on merchant approval of the partner's quote")
        else:
            invite.status = "reservation_failed"
            log(db, "relay_reservation_failed", supplier_id=a.supplier_id, order_id=order.id, allocation_id=a.id,
                relay_id=relay.id, to_state="proposed", qty=a.allocated_qty_base_unit,
                reason="Partner stock changed; the line stays a normal request awaiting the partner's confirmation")
        _notify(db, invite.partner_supplier.user_id, "Relay approved", f"Your relay quote was selected ({invite.status})", None)
    for i in relay.invites:
        if i.id not in selected and i.status in RESPONDABLE:
            i.status = "not_selected"
    db.flush()
    recompute_plan_totals(db, new_plan)
    sync_order_status(db, order)
    for sid in {a.supplier_id for a in new_plan.allocations}:
        recompute_supplier_reliability(db, sid)
    _notify(db, relay.origin_supplier.user_id, "Relay approved by merchant", "Partner supply is now part of the order plan", None)
    db.flush()
    return new_plan


def decline(db: Session, user: User | None, relay: SupplyRelay, note: str, status: str = "declined") -> AllocationPlan | None:
    order = db.get(Order, relay.order_id)
    if not _close(db, relay, status, note, user, "merchant" if user else "system"):
        raise HTTPException(409, f"Relay is {relay.status}")
    for i in relay.invites:
        if i.status in RESPONDABLE:
            i.status = "not_selected"
    origin = db.get(Allocation, relay.origin_allocation_id)
    plan = replan_after_event(db, order, origin, reason="short_supply" if relay.origin_committed_qty_base_unit > EPS else "rejected")
    relay.resolved_plan_id = plan.id
    db.flush()
    return plan


def expire_if_due(db: Session, relay: SupplyRelay) -> bool:
    if relay.status == "open" and relay.expires_at <= now_utc():
        decline(db, None, relay, "Response window closed; standard open-market recovery ran", status="expired")
        return True
    return False


def expire_due_relays(db: Session, order_id: str | None = None) -> None:
    q = db.query(SupplyRelay).filter(SupplyRelay.status == "open", SupplyRelay.expires_at <= now_utc())
    if order_id:
        q = q.filter(SupplyRelay.order_id == order_id)
    for relay in q.all():
        expire_if_due(db, relay)


def relay_view(db: Session, relay: SupplyRelay, viewer: str, viewer_supplier_id: str | None = None) -> dict:
    """Role-scoped representation. Partners never see the merchant's identity, other
    partners' quotes, or the order's other lines."""
    product = relay.product
    base = {
        "id": relay.id, "status": relay.status, "product_name": product.name, "unit": product.base_unit,
        "outstanding_qty": relay.outstanding_qty_base_unit, "price_ceiling": round(relay.price_ceiling_per_base_unit, 2) if relay.price_ceiling_per_base_unit is not None else None,
        "required_brand": relay.required_brand, "needed_by": relay.needed_by, "expires_at": relay.expires_at,
        "created_at": relay.created_at, "resolution_note": relay.resolution_note, "resolved_at": relay.resolved_at,
        "origin_supplier_name": relay.origin_supplier.business_name,
        "origin_committed_qty": relay.origin_committed_qty_base_unit, "reason": relay.reason,
    }
    if viewer == "partner":
        invite = next(i for i in relay.invites if i.partner_supplier_id == viewer_supplier_id)
        elig = invite.eligibility or {}
        return {**base, "invite": {
            "id": invite.id, "status": invite.status, "offered_qty": invite.offered_qty_base_unit,
            "offered_price": invite.offered_price_per_base_unit, "offered_ready_by": invite.offered_ready_by,
            "note": invite.note, "responded_at": invite.responded_at,
            "why_eligible": {k: elig.get(k) for k in ("free_to_promise", "listed_price", "moq", "distance_to_merchant_km", "stock_freshness")},
        }, "merchant": "A merchant on the network (identity withheld until a line is assigned to you)"}
    invites = [{
        "id": i.id, "supplier_id": i.partner_supplier_id, "supplier_name": i.partner_supplier.business_name, "status": i.status,
        "offered_qty": i.offered_qty_base_unit, "offered_price": i.offered_price_per_base_unit,
        "offered_ready_by": i.offered_ready_by, "note": i.note, "responded_at": i.responded_at,
        "eligibility": {k: (i.eligibility or {}).get(k) for k in ("free_to_promise", "listed_price", "reliability_score", "reliability_confidence", "distance_to_merchant_km")},
    } for i in relay.invites]
    return {**base, "order_id": relay.order_id, "invites": invites}
