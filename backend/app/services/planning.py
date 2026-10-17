"""Bridges the database to the pure-function optimizer, and owns the replan/failover
state machine described in the brief:

  rejection | short supply | expired confirmation | recorded disruption
      -> replan_after_event()
      -> excludes the offer that just failed for the rest of this order
      -> re-optimizes only the *outstanding* quantity per item
      -> carries forward everything already confirmed/fulfilled unchanged
      -> produces a new, fully self-contained AllocationPlan (audit trail preserved)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.catalog import Product, SupplierInventory
from app.models.core import SupplierProfile
from app.models.orders import (
    Allocation,
    AllocationPlan,
    AllocationStatus,
    Order,
    OrderStatus,
    SupplierEvent,
    SupplierEventType,
)
from app.services import optimizer
from app.services.geo import estimate_delivery_cost_inr, estimate_distance_km, estimate_duration_minutes
from app.services.reliability import get_or_default_reliability

CONFIRMATION_WINDOW_HOURS = 6
EXCLUDED_TERMINAL_STATUSES = (AllocationStatus.REJECTED, AllocationStatus.EXPIRED, AllocationStatus.SUPERSEDED)


def _effective_qty(a: Allocation) -> float:
    return a.confirmed_qty_base_unit if a.confirmed_qty_base_unit is not None else a.allocated_qty_base_unit


def gather_offers(
    db: Session, product_id: str, merchant_lat: float, merchant_lon: float,
    preferred_supplier_ids: set[str], excluded_offer_ids: set[str],
) -> list[optimizer.OfferCandidate]:
    rows = (
        db.query(SupplierInventory, SupplierProfile)
        .join(SupplierProfile, SupplierInventory.supplier_id == SupplierProfile.id)
        .filter(
            SupplierInventory.product_id == product_id,
            SupplierInventory.is_available.is_(True),
            SupplierProfile.is_active.is_(True),
        )
        .all()
    )
    offers = []
    for inv, supplier in rows:
        # A physical stock count is the freshness evidence; listing edits are the legacy fallback.
        updated = inv.stock_confirmed_at or inv.updated_at
        updated = updated.replace(tzinfo=UTC) if updated.tzinfo is None else updated
        if inv.freshness_source == "stale" or datetime.now(UTC) - updated > timedelta(hours=24):
            continue
        if inv.pack_unit != inv.product.base_unit:
            continue
        if inv.id in excluded_offer_ids:
            continue
        stat = get_or_default_reliability(db, supplier.id)
        distance = estimate_distance_km(merchant_lat, merchant_lon, supplier.latitude, supplier.longitude)
        offers.append(
            optimizer.OfferCandidate(
                offer_id=inv.id,
                supplier_id=supplier.id,
                supplier_name=supplier.business_name,
                product_id=product_id,
                pack_size_base_unit=inv.pack_size,
                price_per_base_unit=inv.price_per_base_unit,
                # Safety stock is never offered to merchants.
                stock_qty_base_unit=max(0.0, inv.stock_qty_base_unit - (inv.safety_stock_base_unit or 0.0)),
                moq_base_unit=inv.moq_base_unit,
                reliability_score=stat.reliability_score,
                reliability_confidence=stat.confidence,
                distance_km=distance,
                is_preferred=supplier.id in preferred_supplier_ids,
            )
        )
    return offers


def _capacities(db: Session, supplier_ids: set[str]) -> dict[str, optimizer.SupplierCapacity]:
    if not supplier_ids:
        return {}
    rows = db.query(SupplierProfile).filter(SupplierProfile.id.in_(supplier_ids)).all()
    return {
        s.id: optimizer.SupplierCapacity(s.id, s.delivery_capacity_kg_per_day) for s in rows
    }


def _persist_allocations(
    db: Session, plan: AllocationPlan, result: optimizer.PlanResult,
    order_item_by_id: dict[str, object],
) -> None:
    for line in result.allocations:
        distance_km = line.distance_km
        route_cost = estimate_delivery_cost_inr(distance_km)
        route_duration = estimate_duration_minutes(distance_km)
        alloc = Allocation(
            plan_id=plan.id,
            inventory_id=line.offer_id,
            order_item_id=line.order_item_id,
            supplier_id=line.supplier_id,
            product_id=line.product_id,
            allocated_qty_base_unit=line.allocated_qty_base_unit,
            unit_price=line.unit_price,
            pack_count=line.pack_count,
            status=AllocationStatus.PROPOSED,
            route_distance_km=distance_km,
            route_duration_minutes=route_duration,
            route_cost=route_cost,
            confirmation_expires_at=datetime.now(UTC) + timedelta(hours=CONFIRMATION_WINDOW_HOURS),
        )
        db.add(alloc)
    db.flush()


def recompute_plan_totals(db: Session, plan: AllocationPlan) -> None:
    included = [a for a in plan.allocations if a.status not in EXCLUDED_TERMINAL_STATUSES]
    total_product_cost = 0.0
    total_risk = 0.0
    suppliers_route_cost: dict[str, float] = {}
    max_duration_minutes = 0.0
    for a in included:
        qty = _effective_qty(a)
        total_product_cost += qty * a.unit_price
        stat = get_or_default_reliability(db, a.supplier_id)
        total_risk += qty * a.unit_price * (1 - stat.reliability_score)
        if qty <= 0:
            continue
        suppliers_route_cost[a.supplier_id] = max(a.route_cost, suppliers_route_cost.get(a.supplier_id, 0))
        max_duration_minutes = max(max_duration_minutes, a.route_duration_minutes or 0.0)

    total_delivery_cost = sum(suppliers_route_cost.values())
    plan.total_product_cost = round(total_product_cost, 2)
    plan.total_delivery_cost = round(total_delivery_cost, 2)
    plan.total_risk_penalty = round(total_risk, 2)
    plan.total_cost = round(total_product_cost + total_delivery_cost, 2)
    plan.supplier_count = len(suppliers_route_cost)
    plan.estimated_delivery_hours = round(max_duration_minutes / 60.0, 2)


def create_initial_plans(db: Session, order: Order) -> list[AllocationPlan]:
    from app.models.core import MerchantProfile

    merchant = db.get(MerchantProfile, order.merchant_id)
    preferred = set(order.preferred_supplier_ids or [])

    items = []
    offers_by_product: dict[str, list[optimizer.OfferCandidate]] = {}
    product_names: dict[str, str] = {}
    for item in order.items:
        product = db.get(Product, item.product_id)
        product_names[item.product_id] = product.name if product else item.product_id
        items.append(
            optimizer.ItemRequest(
                order_item_id=item.id,
                product_id=item.product_id,
                product_name=product_names[item.product_id],
                requested_qty_base_unit=item.requested_qty_base_unit,
                substitution_allowed=item.substitution_allowed,
                base_unit=product.base_unit,
            )
        )
        offers_by_product[item.product_id] = gather_offers(
            db, item.product_id, merchant.latitude, merchant.longitude, preferred, excluded_offer_ids=set()
        )

    all_supplier_ids = {o.supplier_id for offers in offers_by_product.values() for o in offers}
    capacities = _capacities(db, all_supplier_ids)

    plans = []
    for profile in ("cheapest", "fastest", "most_reliable"):
        policy = optimizer.OptimizerPolicy(
            objective_profile=profile,
            budget_cap=order.budget_cap,
            price_tolerance_pct=order.price_tolerance_pct,
            min_reliability=order.min_reliability,
            max_suppliers=order.max_suppliers,
        )
        result = optimizer.solve_allocation(items, offers_by_product, capacities, policy)

        plan = AllocationPlan(
            order_id=order.id,
            objective_profile=profile,
            is_selected=False,
            is_feasible=result.is_feasible,
            replan_reason="initial",
            infeasible_reasons=result.infeasible_reasons,
            explanation={"excluded_offers": result.excluded_offers, "shortfall_by_item": result.shortfall_by_item, "supply_basis": "quotes updated within 24h; not reservations", "price_ceilings": {pid: min(o.price_per_base_unit for o in offers if o.reliability_score >= order.min_reliability) * (1 + order.price_tolerance_pct / 100) for pid, offers in offers_by_product.items() if any(o.reliability_score >= order.min_reliability for o in offers)}},
        )
        db.add(plan)
        db.flush()
        _persist_allocations(db, plan, result, {})
        db.refresh(plan)
        recompute_plan_totals(db, plan)
        plans.append(plan)

    order.status = OrderStatus.PLANNED
    db.flush()
    return plans


def outstanding_by_item(order: Order, plan: AllocationPlan, exclude_allocation_id: str | None = None) -> dict[str, float]:
    """Requested minus everything secured or still pending on `plan`, per order item."""
    out: dict[str, float] = {}
    for item in order.items:
        secured = 0.0
        for a in plan.allocations:
            if a.order_item_id != item.id:
                continue
            if a.status in (AllocationStatus.CONFIRMED, AllocationStatus.FULFILLED, AllocationStatus.SHORT_SUPPLY):
                secured += _effective_qty(a)
            elif a.status == AllocationStatus.PROPOSED and a.id != exclude_allocation_id:
                secured += a.allocated_qty_base_unit  # still pending, assume it will land
        out[item.id] = max(0.0, round(item.requested_qty_base_unit - secured, 3))
    return out


def open_relays(db: Session, order: Order) -> list:
    from app.models.continuity import SupplyRelay
    return db.query(SupplyRelay).filter(SupplyRelay.order_id == order.id, SupplyRelay.status == "open").all()


def select_plan(db: Session, order: Order, plan_id: str) -> AllocationPlan:
    for plan in order.plans:
        if plan.id == plan_id:
            plan.is_selected = True
        elif plan.is_selected:
            plan.is_selected = False
            for a in plan.allocations:
                if a.status == AllocationStatus.PROPOSED:
                    a.status = AllocationStatus.SUPERSEDED
    order.status = OrderStatus.AWAITING_CONFIRMATION
    db.flush()
    selected = next(p for p in order.plans if p.id == plan_id)
    from app.services.notify import announce_new_requests
    announce_new_requests(db, selected)
    return selected


def get_selected_plan(order: Order) -> AllocationPlan | None:
    return next((p for p in order.plans if p.is_selected), None)


def sync_order_status(db: Session, order: Order) -> None:
    """Derives order.status from the current selected plan's allocation states.
    Called after every confirm/reject/shortfall/replan so the order status always
    reflects reality rather than being set ad hoc in each call site.

    A SHORT_SUPPLY/REJECTED/EXPIRED allocation is "resolved" for this purpose as long
    as nothing is still PROPOSED (awaiting a supplier's response) -- its shortfall, if
    any, has already been handed to a replan that produced its own PROPOSED lines.
    """
    plan = get_selected_plan(order)
    if plan is None:
        return
    if open_relays(db, order):
        # A supplier relay is collecting partner responses for an uncovered quantity.
        order.status = OrderStatus.REPLANNING
        db.flush()
        return
    active = [a for a in plan.allocations if a.status not in EXCLUDED_TERMINAL_STATUSES and _effective_qty(a) > 0]
    if not active:
        order.status = OrderStatus.INFEASIBLE
        return
    if any(a.status == AllocationStatus.PROPOSED for a in active):
        order.status = (
            OrderStatus.REPLANNING if order.status in (OrderStatus.REPLANNING, OrderStatus.INFEASIBLE)
            else OrderStatus.AWAITING_CONFIRMATION
        )
    elif all(a.status == AllocationStatus.FULFILLED for a in active) and plan.is_feasible:
        order.status = OrderStatus.FULFILLED
    elif not plan.is_feasible:
        order.status = OrderStatus.INFEASIBLE
    else:
        order.status = OrderStatus.CONFIRMED
    db.flush()


def _all_excluded_offer_ids(db: Session, order: Order) -> set[str]:
    """Offers that have already failed (rejected/expired/short-supplied) anywhere in
    this order's history are never re-suggested for the same order."""
    excluded = set()
    for plan in order.plans:
        for a in plan.allocations:
            if a.status in (AllocationStatus.REJECTED, AllocationStatus.EXPIRED, AllocationStatus.SHORT_SUPPLY):
                inv = (
                    db.query(SupplierInventory)
                    .filter(
                        SupplierInventory.supplier_id == a.supplier_id,
                        SupplierInventory.product_id == a.product_id,
                    )
                    .first()
                )
                if inv:
                    excluded.add(inv.id)
    return excluded


def build_recovery_problem(
    db: Session, order: Order, plan: AllocationPlan, outstanding: dict[str, float],
    excluded_offer_ids: set[str], offers_override: dict[str, list[optimizer.OfferCandidate]] | None = None,
) -> tuple[list, dict, dict, optimizer.OptimizerPolicy] | None:
    """Optimizer inputs for covering `outstanding` on top of what `plan` already holds:
    remaining budget, original price ceiling, supplier limit and remaining capacity.
    Shared by the real replan and the read-only Supply Relay preview so both apply
    exactly the same merchant policy."""
    from app.models.core import MerchantProfile

    merchant = db.get(MerchantProfile, order.merchant_id)
    preferred = set(order.preferred_supplier_ids or [])
    items = []
    offers_by_product: dict[str, list[optimizer.OfferCandidate]] = {}
    for item in order.items:
        item_outstanding = outstanding.get(item.id, 0.0)
        if item_outstanding <= 1e-6:
            continue
        product = db.get(Product, item.product_id)
        items.append(
            optimizer.ItemRequest(
                order_item_id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else item.product_id,
                requested_qty_base_unit=item_outstanding,
                substitution_allowed=item.substitution_allowed,
                base_unit=product.base_unit,
            )
        )
        if offers_override is not None and item.product_id in offers_override:
            offers_by_product[item.product_id] = offers_override[item.product_id]
        else:
            offers_by_product[item.product_id] = gather_offers(
                db, item.product_id, merchant.latitude, merchant.longitude, preferred, excluded_offer_ids
            )
    if not items:
        return None

    committed = [a for a in plan.allocations if a.status not in EXCLUDED_TERMINAL_STATUSES and _effective_qty(a) > 0]
    committed_ids = {a.supplier_id for a in committed}
    for offers in offers_by_product.values():
        for offer in offers:
            pending = sum(_effective_qty(a) for a in committed if a.inventory_id == offer.offer_id and a.status == AllocationStatus.PROPOSED)
            offer.stock_qty_base_unit = max(0, offer.stock_qty_base_unit - pending)
    all_supplier_ids = {o.supplier_id for offers in offers_by_product.values() for o in offers}
    capacities = _capacities(db, all_supplier_ids)
    policy = optimizer.OptimizerPolicy(
        objective_profile=plan.objective_profile,
        budget_cap=max(0, order.budget_cap - plan.total_cost) if order.budget_cap is not None else None,
        price_tolerance_pct=order.price_tolerance_pct,
        min_reliability=order.min_reliability,
        max_suppliers=order.max_suppliers,
        committed_supplier_ids=committed_ids,
        price_ceiling_by_product=initial_price_ceilings(order),
    )
    for sid, cap in capacities.items():
        cap.delivery_capacity_kg_per_day = max(0, cap.delivery_capacity_kg_per_day - sum(_effective_qty(a) for a in committed if a.supplier_id == sid and a.product.base_unit == "kg"))
    return items, offers_by_product, capacities, policy


def initial_price_ceilings(order: Order) -> dict[str, float]:
    return next((p.explanation.get("price_ceilings", {}) for p in order.plans if p.replan_reason == "initial"), {})


def replan_after_event(
    db: Session, order: Order, trigger_allocation: Allocation, reason: str,
    offers_override: dict[str, list[optimizer.OfferCandidate]] | None = None,
    keep_relay_id: str | None = None,
) -> AllocationPlan:
    """`offers_override` replaces the open-market offers for the given products (the
    Supply Relay passes partner quotes here); every other rule is unchanged."""
    from app.services.promise import log

    current_plan = get_selected_plan(order)
    if current_plan is None:
        raise ValueError("Order has no selected plan to replan from")

    # This replan covers the outstanding quantity itself, so any open relay for the
    # order would double-source it: close the relay and say why.
    for relay in open_relays(db, order):
        if relay.id == keep_relay_id:
            continue
        relay.status = "superseded"
        relay.resolution_note = f"Order replanned ({reason}); open-market recovery now covers the outstanding quantity"
        relay.resolved_at = datetime.now(UTC)
        log(db, "relay_superseded", order_id=order.id, relay_id=relay.id, supplier_id=relay.origin_supplier_id,
            from_state="open", to_state="superseded", reason=relay.resolution_note)

    excluded_offer_ids = _all_excluded_offer_ids(db, order)

    outstanding = outstanding_by_item(order, current_plan, exclude_allocation_id=trigger_allocation.id)

    new_plan = AllocationPlan(
        order_id=order.id,
        objective_profile=current_plan.objective_profile,
        is_selected=True,
        is_feasible=True,
        replan_reason=reason,
    )
    db.add(new_plan)
    db.flush()
    # order.plans may already be loaded; without this, sync_order_status cannot see the
    # new selected plan and silently leaves the order status unchanged.
    db.expire(order, ["plans"])

    # Carry forward every non-superseded allocation from the old plan except the
    # trigger (which gets re-added in its final failed/short-supply state).
    carried_ids = set()
    for a in current_plan.allocations:
        if a.status in (AllocationStatus.SUPERSEDED,):
            continue
        copy = Allocation(
            plan_id=new_plan.id,
            inventory_id=a.inventory_id,
            order_item_id=a.order_item_id,
            supplier_id=a.supplier_id,
            product_id=a.product_id,
            allocated_qty_base_unit=a.allocated_qty_base_unit,
            unit_price=a.unit_price,
            pack_count=a.pack_count,
            status=a.status,
            confirmed_qty_base_unit=a.confirmed_qty_base_unit,
            confirmed_ready_by=a.confirmed_ready_by,
            confirmation_expires_at=a.confirmation_expires_at,
            route_distance_km=a.route_distance_km,
            route_duration_minutes=a.route_duration_minutes,
            route_source=a.route_source,
            route_cost=a.route_cost,
            fulfillment_stage=a.fulfillment_stage,
        )
        db.add(copy)
        carried_ids.add(a.id)
    current_plan.is_selected = False
    db.flush()

    db.refresh(new_plan)
    recompute_plan_totals(db, new_plan)
    problem = build_recovery_problem(db, order, new_plan, outstanding, excluded_offer_ids, offers_override)
    if problem is not None:
        items, offers_by_product, capacities, policy = problem
        result = optimizer.solve_allocation(items, offers_by_product, capacities, policy)
        new_plan.is_feasible = result.is_feasible
        new_plan.infeasible_reasons = result.infeasible_reasons
        new_plan.explanation = {"excluded_offers": result.excluded_offers, "outstanding_by_item": outstanding, "shortfall_by_item": result.shortfall_by_item, "budget_remaining_before_recovery": policy.budget_cap, "previous_plan_id": current_plan.id}
        _persist_allocations(db, new_plan, result, {})
    else:
        new_plan.infeasible_reasons = []
        new_plan.explanation = {"outstanding_by_item": outstanding}

    db.flush()
    db.refresh(new_plan)
    recompute_plan_totals(db, new_plan)

    order.status = OrderStatus.REPLANNING
    sync_order_status(db, order)
    from app.services.notify import announce_replan
    announce_replan(db, order, new_plan, reason)
    return new_plan


def expire_overdue_allocations(db: Session, order: Order) -> bool:
    """Lazily flips PROPOSED allocations whose confirmation window has passed to
    EXPIRED and triggers a replan. Returns True if anything changed."""
    plan = get_selected_plan(order)
    if plan is None:
        return False
    now = datetime.now(UTC)
    changed = False
    for a in list(plan.allocations):
        if a.status != AllocationStatus.PROPOSED or a.confirmation_expires_at is None:
            continue
        expires_at = a.confirmation_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            a.status = AllocationStatus.EXPIRED
            db.add(SupplierEvent(allocation_id=a.id, event_type=SupplierEventType.EXPIRED, payload={}, triggered_replan=True))
            db.flush()
            replan_after_event(db, order, a, reason="confirmation_expired")
            return True  # next read handles another expiry on the new selected plan
    return changed


def plan_survival_basket(
    db: Session,
    merchant_lat: float,
    merchant_lon: float,
    items: list[dict],
    budget_cap: float,
    price_tolerance_pct: float,
    min_reliability: float,
    max_suppliers: int,
) -> dict:
    """Merchant Survival Mode: a dry-run preview (nothing is persisted) that ranks
    items by merchant-supplied priority (1 = highest) and spends the budget tier by
    tier, calling the *same* CP-SAT solver used for real orders once per tier with the
    budget remaining after higher-priority tiers. This is not a separate heuristic --
    it is the real optimizer, invoked with a shrinking budget constraint.

    `items`: [{"product_id", "product_name", "requested_qty_base_unit", "priority"}]
    """
    by_priority: dict[int, list[dict]] = {}
    for item in items:
        by_priority.setdefault(item["priority"], []).append(item)

    remaining_budget = budget_cap
    tiers_result = []
    used_supplier_ids: set[str] = set()
    used_capacity: dict[str, float] = {}
    unfulfilled: list[dict] = []

    for priority in sorted(by_priority.keys()):
        tier_items_raw = by_priority[priority]
        tier_items = [
            optimizer.ItemRequest(
                order_item_id=it["product_id"],  # no real OrderItem yet in a dry run; product_id is unique per tier call
                product_id=it["product_id"], product_name=it["product_name"],
                requested_qty_base_unit=it["requested_qty_base_unit"], substitution_allowed=True,
                base_unit=db.get(Product, it["product_id"]).base_unit,
            )
            for it in tier_items_raw
        ]
        offers_by_product = {
            it.product_id: gather_offers(db, it.product_id, merchant_lat, merchant_lon, set(), set())
            for it in tier_items
        }
        all_supplier_ids = {o.supplier_id for offers in offers_by_product.values() for o in offers}
        capacities = _capacities(db, all_supplier_ids)
        policy = optimizer.OptimizerPolicy(
            objective_profile="cheapest", budget_cap=max(0.0, remaining_budget),
            price_tolerance_pct=price_tolerance_pct, min_reliability=min_reliability, max_suppliers=max_suppliers,
            committed_supplier_ids=used_supplier_ids,
        )
        for sid, cap in capacities.items():
            cap.delivery_capacity_kg_per_day = max(0, cap.delivery_capacity_kg_per_day - used_capacity.get(sid, 0))
        result = optimizer.solve_allocation(tier_items, offers_by_product, capacities, policy)

        tier_spend = result.total_cost
        remaining_budget = max(0.0, remaining_budget - tier_spend)

        for line in result.allocations:
            used_supplier_ids.add(line.supplier_id)
            if db.get(Product, line.product_id).base_unit == "kg":
                used_capacity[line.supplier_id] = used_capacity.get(line.supplier_id, 0) + line.allocated_qty_base_unit
        for it in tier_items_raw:
            shortfall = result.shortfall_by_item.get(it["product_id"], it["requested_qty_base_unit"])
            if shortfall > 1e-6:
                unfulfilled.append({**it, "shortfall_qty_base_unit": round(shortfall, 3)})

        tiers_result.append(
            {
                "priority": priority,
                "items": [it["product_name"] for it in tier_items_raw],
                "is_feasible": result.is_feasible,
                "allocations": [
                    {
                        "product_id": line.product_id, "supplier_id": line.supplier_id,
                        "allocated_qty_base_unit": line.allocated_qty_base_unit, "unit_price": line.unit_price,
                    }
                    for line in result.allocations
                ],
                "tier_cost": round(tier_spend, 2),
                "shortfall_by_item": result.shortfall_by_item,
                "infeasible_reasons": result.infeasible_reasons,
            }
        )

    return {
        "tiers": tiers_result,
        "total_spent": round(budget_cap - remaining_budget, 2),
        "budget_cap": budget_cap,
        "remaining_budget": round(remaining_budget, 2),
        "fully_unfulfilled_items": unfulfilled,
    }
