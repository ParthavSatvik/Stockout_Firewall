"""PromiseGuard: what a supplier can responsibly promise, and how safe its promises are.

Quantity model for one inventory row (all in the product's base unit):

    uncommitted     = SupplierInventory.stock_qty_base_unit  (confirmations deduct atomically)
    committed       = confirmed quantity on live commitments still in the warehouse
                      (stage reserved | picking | ready)
    on_hand         = uncommitted + committed                (derived, never double counted)
    safety_stock    = SupplierInventory.safety_stock_base_unit
    free_to_promise = max(0, uncommitted - safety_stock)
    requested       = open requests awaiting this supplier's decision (NOT reserved)
    in_transit      = dispatched, not yet delivered

Every rule here is deterministic and its inputs are returned with the result. Nothing
in this module is a trained model, and nothing here changes state except
`record_stock_count` and `reserve_stock`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.catalog import Product, SupplierInventory
from app.models.continuity import CommitmentLedgerEntry
from app.models.core import SupplierProfile
from app.models.orders import Allocation, AllocationPlan, AllocationStatus

IST = timezone(timedelta(hours=5, minutes=30))  # India has no DST
FRESH_HOURS = 12
STALE_HOURS = 24  # matches the planner's offer cutoff in planning.gather_offers
LIVE_STATUSES = (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY)
STAGES = ("reserved", "picking", "ready", "dispatched", "delivered")
WAREHOUSE_STAGES = ("reserved", "picking", "ready")
EPS = 1e-6


def now_utc() -> datetime:
    return datetime.now(UTC)


def stage_of(a: Allocation) -> str | None:
    if a.status == AllocationStatus.PROPOSED:
        return "quote"
    if a.status == AllocationStatus.FULFILLED:
        return "delivered"
    if a.status in LIVE_STATUSES:
        return a.fulfillment_stage or "reserved"  # legacy confirmations predate stages
    return None


def committed_qty(a: Allocation) -> float:
    return a.confirmed_qty_base_unit or 0.0


def log(db: Session, action: str, *, actor_user_id: str | None = None, actor_role: str = "system",
        supplier_id: str | None = None, order_id: str | None = None, allocation_id: str | None = None,
        inventory_id: str | None = None, relay_id: str | None = None, from_state: str | None = None,
        to_state: str | None = None, qty: float | None = None, reason: str = "", payload: dict | None = None,
        visible_to_merchant: bool = True) -> CommitmentLedgerEntry:
    entry = CommitmentLedgerEntry(
        actor_user_id=actor_user_id, actor_role=actor_role, supplier_id=supplier_id, order_id=order_id,
        allocation_id=allocation_id, inventory_id=inventory_id, relay_id=relay_id, action=action,
        from_state=from_state, to_state=to_state, qty_base_unit=qty, reason=reason[:300],
        payload=payload or {}, visible_to_merchant=visible_to_merchant,
    )
    db.add(entry)
    return entry


def live_allocations(db: Session, supplier_id: str) -> list[Allocation]:
    """Allocations on each order's currently selected plan. Replans copy lines into a
    new plan, so restricting to selected plans counts every commitment exactly once."""
    return (
        db.query(Allocation).join(AllocationPlan, Allocation.plan_id == AllocationPlan.id)
        .filter(AllocationPlan.is_selected.is_(True), Allocation.supplier_id == supplier_id)
        .all()
    )


def stock_freshness(inv: SupplierInventory, now: datetime | None = None) -> dict:
    now = now or now_utc()
    if inv.stock_confirmed_at is not None:
        at, source = inv.stock_confirmed_at, "stock_count"
    else:
        at, source = inv.updated_at, "last_listing_edit"
    age_h = max(0.0, (now - at).total_seconds() / 3600) if at else None
    if age_h is None:
        status = "unknown"
    elif age_h <= FRESH_HOURS:
        status = "fresh"
    elif age_h <= STALE_HOURS:
        status = "aging"
    else:
        status = "stale"
    return {"confirmed_at": at, "source": source, "age_hours": round(age_h, 1) if age_h is not None else None,
            "status": status, "excluded_from_new_plans": status == "stale"}


@dataclass
class InventoryPosition:
    inventory: SupplierInventory
    product: Product
    uncommitted: float
    committed: float
    on_hand: float
    safety_stock: float
    free_to_promise: float
    requested: float
    in_transit: float
    delivered: float
    freshness: dict
    drift_qty: float  # how far the last physical count fell short of live commitments
    commitments: list[Allocation] = field(default_factory=list)
    requests: list[Allocation] = field(default_factory=list)

    def as_dict(self) -> dict:
        inv = self.inventory
        return {
            "inventory_id": inv.id, "product_id": self.product.id, "product_name": self.product.name,
            "unit": self.product.base_unit, "brand": inv.brand, "pack_size": inv.pack_size,
            "price_per_base_unit": inv.price_per_base_unit, "moq_base_unit": inv.moq_base_unit,
            "is_available": inv.is_available,
            "on_hand": round(self.on_hand, 3), "reported_on_hand": inv.reported_on_hand_base_unit,
            "committed": round(self.committed, 3), "safety_stock": round(self.safety_stock, 3),
            "uncommitted": round(self.uncommitted, 3), "free_to_promise": round(self.free_to_promise, 3),
            "requested_pending": round(self.requested, 3), "in_transit": round(self.in_transit, 3),
            "delivered": round(self.delivered, 3), "oversubscribed_by": round(max(0.0, self.requested - self.free_to_promise), 3),
            "drift_qty": round(self.drift_qty, 3), "freshness": self.freshness,
            "formula": "free_to_promise = max(0, on_hand - committed - safety_stock)",
        }


def positions(db: Session, supplier_id: str) -> list[InventoryPosition]:
    invs = db.query(SupplierInventory).filter(SupplierInventory.supplier_id == supplier_id).all()
    by_inv: dict[str, list[Allocation]] = {}
    for a in live_allocations(db, supplier_id):
        if a.inventory_id:
            by_inv.setdefault(a.inventory_id, []).append(a)
    now = now_utc()
    out = []
    for inv in invs:
        lines = by_inv.get(inv.id, [])
        commitments = [a for a in lines if a.status in LIVE_STATUSES and stage_of(a) in WAREHOUSE_STAGES]
        committed = sum(committed_qty(a) for a in commitments)
        in_transit = sum(committed_qty(a) for a in lines if a.status in LIVE_STATUSES and stage_of(a) == "dispatched")
        delivered = sum(committed_qty(a) for a in lines if a.status == AllocationStatus.FULFILLED)
        requests = [a for a in lines if a.status == AllocationStatus.PROPOSED]
        uncommitted = max(0.0, inv.stock_qty_base_unit)
        reported = inv.reported_on_hand_base_unit
        out.append(InventoryPosition(
            inventory=inv, product=inv.product, uncommitted=uncommitted, committed=committed,
            on_hand=uncommitted + committed, safety_stock=inv.safety_stock_base_unit or 0.0,
            free_to_promise=max(0.0, uncommitted - (inv.safety_stock_base_unit or 0.0)) if inv.is_available else 0.0,
            requested=sum(a.allocated_qty_base_unit for a in requests), in_transit=in_transit, delivered=delivered,
            freshness=stock_freshness(inv, now),
            drift_qty=max(0.0, committed - reported) if reported is not None else 0.0,
            commitments=commitments, requests=requests,
        ))
    return out


def position_for(db: Session, inv: SupplierInventory) -> InventoryPosition:
    return next(p for p in positions(db, inv.supplier_id) if p.inventory.id == inv.id)


# --------------------------------------------------------------------------- writes

def reserve_stock(db: Session, inventory_id: str, qty: float, *, allow_safety_stock: bool = False) -> bool:
    """Atomic conditional decrement. Two concurrent promises can never both succeed
    against the same units: the WHERE clause re-checks availability in the UPDATE."""
    if qty <= EPS:
        return True
    floor = 0.0 if allow_safety_stock else SupplierInventory.safety_stock_base_unit
    changed = db.execute(update(SupplierInventory).where(
        SupplierInventory.id == inventory_id,
        SupplierInventory.is_available.is_(True),
        SupplierInventory.stock_qty_base_unit - floor >= qty - EPS,
    ).values(stock_qty_base_unit=SupplierInventory.stock_qty_base_unit - qty))
    return changed.rowcount == 1


def record_stock_count(db: Session, supplier: SupplierProfile, inv: SupplierInventory, on_hand: float,
                       actor_user_id: str, safety_stock: float | None = None, reason: str = "") -> dict:
    """A physical count. Live commitments are subtracted so they are not promised twice;
    a count below what is already committed is recorded as commitment drift."""
    before = position_for(db, inv)
    if safety_stock is not None:
        inv.safety_stock_base_unit = safety_stock
    inv.reported_on_hand_base_unit = on_hand
    inv.stock_qty_base_unit = max(0.0, on_hand - before.committed)
    inv.stock_confirmed_at = now_utc()
    inv.freshness_source = "manual"
    drift = max(0.0, before.committed - on_hand)
    log(db, "stock_count", actor_user_id=actor_user_id, actor_role="supplier", supplier_id=supplier.id,
        inventory_id=inv.id, qty=on_hand, reason=reason, visible_to_merchant=False,
        payload={"previous_on_hand": round(before.on_hand, 3), "committed": round(before.committed, 3),
                 "safety_stock": inv.safety_stock_base_unit, "uncommitted_after": inv.stock_qty_base_unit})
    if drift > EPS:
        log(db, "commitment_drift_detected", actor_user_id=actor_user_id, actor_role="supplier",
            supplier_id=supplier.id, inventory_id=inv.id, qty=drift, visible_to_merchant=False,
            reason=f"Counted {on_hand:g} but {before.committed:g} is already committed")
    db.flush()
    return {"drift_qty": drift, "committed": before.committed}


# ------------------------------------------------------------------- operating window

def _parse_hours(text: str) -> tuple[int, int]:
    try:
        start, end = text.split("-")
        return int(start.split(":")[0]) * 60 + int(start.split(":")[1]), int(end.split(":")[0]) * 60 + int(end.split(":")[1])
    except (ValueError, IndexError):
        return 9 * 60, 20 * 60


def within_hours(supplier: SupplierProfile, when: datetime) -> bool:
    start, end = _parse_hours(supplier.operating_hours)
    local = when.astimezone(IST)
    minute = local.hour * 60 + local.minute
    return start <= minute <= end


def next_open_slot(supplier: SupplierProfile, earliest: datetime) -> datetime:
    start, end = _parse_hours(supplier.operating_hours)
    local = earliest.astimezone(IST)
    minute = local.hour * 60 + local.minute
    if minute < start:
        local = local.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
    elif minute > end:
        local = (local + timedelta(days=1)).replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
    return local.astimezone(UTC)


def day_load(db: Session, supplier_id: str, day, exclude_allocation_id: str | None = None) -> float:
    """kg of live warehouse commitments due to be ready on an IST calendar day."""
    total = 0.0
    for a in live_allocations(db, supplier_id):
        if a.id == exclude_allocation_id or a.status not in LIVE_STATUSES or stage_of(a) not in WAREHOUSE_STAGES:
            continue
        if a.confirmed_ready_by is None or a.product.base_unit != "kg":
            continue
        if a.confirmed_ready_by.astimezone(IST).date() == day:
            total += committed_qty(a)
    return total


def suggest_ready_by(db: Session, supplier: SupplierProfile, qty: float, unit: str, lead_hours: float = 3.0) -> dict:
    earliest = (now_utc() + timedelta(hours=lead_hours)).replace(second=0, microsecond=0)
    earliest += timedelta(minutes=(30 - earliest.minute % 30) % 30)  # round up to the half hour
    slot = next_open_slot(supplier, earliest)
    if unit != "kg":
        return {"ready_by": slot, "basis": f"{lead_hours:g}h preparation lead time within operating hours {supplier.operating_hours} IST"}
    for _ in range(14):
        load = day_load(db, supplier.id, slot.astimezone(IST).date())
        if load + qty <= supplier.delivery_capacity_kg_per_day + EPS:
            return {"ready_by": slot, "basis": f"first slot in operating hours with daily capacity ({load:g} + {qty:g} ≤ {supplier.delivery_capacity_kg_per_day:g} kg)"}
        slot = next_open_slot(supplier, (slot.astimezone(IST) + timedelta(days=1)).replace(hour=0, minute=0).astimezone(UTC))
    return {"ready_by": None, "basis": "no day within 14 days has spare daily capacity for this quantity"}


# ------------------------------------------------------------------------- guard

GUARD_LABELS = {
    "SAFE_TO_COMMIT": "Safe to commit",
    "PARTIAL_COMMITMENT_RECOMMENDED": "Partial commitment recommended",
    "DELIVERY_WINDOW_AT_RISK": "Delivery window at risk",
    "COMMITMENT_CONFLICT": "Commitment conflict",
    "NO_FREE_STOCK": "No free stock",
    "INSUFFICIENT_DATA": "Insufficient data",
}


def _age(hours: float | None) -> str:
    if hours is None:
        return "never"
    return "under an hour ago" if hours < 1 else f"{hours:.0f}h ago"


def assess_request(db: Session, supplier: SupplierProfile, alloc: Allocation, ready_by: datetime | None = None) -> dict:
    """Pre-commitment check for a request awaiting this supplier's decision."""
    product = alloc.product
    requested = alloc.allocated_qty_base_unit
    checks: list[dict] = []
    inv = db.get(SupplierInventory, alloc.inventory_id) if alloc.inventory_id else None
    if inv is None:
        return {"status": "INSUFFICIENT_DATA", "label": GUARD_LABELS["INSUFFICIENT_DATA"], "requested": requested,
                "max_feasible_qty": 0.0, "checks": [{"rule": "inventory_link", "ok": False,
                "detail": "This request predates inventory references; it cannot be validated against stock."}]}

    pos = position_for(db, inv)
    others = [a for a in pos.requests if a.id != alloc.id]
    other_requested = sum(a.allocated_qty_base_unit for a in others)
    ftp = pos.free_to_promise
    unit = product.base_unit

    sku_ok = inv.product_id == alloc.product_id and inv.pack_unit == product.base_unit
    checks.append({"rule": "sku_and_unit", "ok": sku_ok,
                   "detail": f"{product.name}, {inv.brand}, {inv.pack_size:g} {inv.pack_unit} packs; quantities normalised to {unit}"})
    fresh = pos.freshness
    checks.append({"rule": "stock_freshness", "ok": fresh["status"] in ("fresh", "aging"),
                   "detail": f"Stock last confirmed {_age(fresh['age_hours'])} via {fresh['source'].replace('_', ' ')} ({fresh['status']})"})
    checks.append({"rule": "free_to_promise", "ok": ftp + EPS >= requested,
                   "detail": f"{pos.on_hand:g} on hand − {pos.committed:g} committed − {pos.safety_stock:g} safety = {ftp:g} {unit} free"})
    if others:
        checks.append({"rule": "competing_requests", "ok": requested + other_requested <= ftp + EPS,
                       "detail": f"{len(others)} other open request(s) want {other_requested:g} {unit} of the same stock; first confirmed is first reserved"})

    full_packs = int((min(requested, ftp) + EPS) // inv.pack_size) if inv.pack_size else 0
    loose = round(min(requested, ftp) - full_packs * inv.pack_size, 3)

    window: dict = {}
    if ready_by is not None:
        in_hours = within_hours(supplier, ready_by)
        window_ok = ready_by > now_utc()
        checks.append({"rule": "ready_by_in_future", "ok": window_ok, "detail": f"Ready-by {ready_by.astimezone(IST):%d %b %H:%M} IST"})
        checks.append({"rule": "operating_hours", "ok": in_hours, "detail": f"Operating hours {supplier.operating_hours} IST"})
        capacity_ok = True
        if unit == "kg":
            load = day_load(db, supplier.id, ready_by.astimezone(IST).date(), exclude_allocation_id=alloc.id)
            capacity_ok = load + min(requested, ftp) <= supplier.delivery_capacity_kg_per_day + EPS
            checks.append({"rule": "daily_capacity", "ok": capacity_ok,
                           "detail": f"{load:g} kg already due that day + {min(requested, ftp):g} kg vs {supplier.delivery_capacity_kg_per_day:g} kg/day capacity"})
        window = {"ok": window_ok and in_hours and capacity_ok}

    if not sku_ok or fresh["status"] in ("stale", "unknown"):
        status = "INSUFFICIENT_DATA"
        headline = ("Stock record is stale — count stock before promising." if sku_ok
                    else "Inventory record does not match the requested product/unit.")
    elif ftp <= EPS:
        status = "COMMITMENT_CONFLICT" if pos.committed + pos.safety_stock > EPS and pos.on_hand > EPS else "NO_FREE_STOCK"
        headline = (f"All {pos.on_hand:g} {unit} on hand is already committed or held as safety stock."
                    if status == "COMMITMENT_CONFLICT" else f"No {product.name} recorded in stock.")
    elif ftp + EPS < requested:
        status = "PARTIAL_COMMITMENT_RECOMMENDED"
        headline = f"Only {ftp:g} of {requested:g} {unit} can be promised without breaking existing commitments."
    elif window and not window["ok"]:
        status = "DELIVERY_WINDOW_AT_RISK"
        headline = "Stock is sufficient but the chosen ready-by time conflicts with hours or capacity."
    else:
        status = "SAFE_TO_COMMIT"
        headline = f"{requested:g} {unit} fits within {ftp:g} {unit} free to promise."

    max_feasible = round(min(requested, ftp), 3) if status not in ("INSUFFICIENT_DATA",) else 0.0
    suggestion = suggest_ready_by(db, supplier, max_feasible or requested, unit) if max_feasible > 0 else {"ready_by": None, "basis": "nothing can be committed"}
    shortfall = round(max(0.0, requested - max_feasible), 3)
    return {
        "status": status, "label": GUARD_LABELS[status], "headline": headline,
        "requested": requested, "unit": unit, "max_feasible_qty": max_feasible, "shortfall_qty": shortfall,
        "pack_breakdown": {"pack_size": inv.pack_size, "full_packs": full_packs, "loose_qty": loose},
        "unit_price": alloc.unit_price, "revenue_at_max": round(max_feasible * alloc.unit_price, 2),
        "revenue_forgone": round(shortfall * alloc.unit_price, 2),
        "margin_note": "Margin is not shown: purchase cost is not recorded in Stockout Firewall.",
        "suggested_ready_by": suggestion["ready_by"], "suggestion_basis": suggestion["basis"],
        "position": pos.as_dict(), "checks": checks,
        "consequence_if_ignored": (f"The request expires at {alloc.confirmation_expires_at.astimezone(IST):%d %b %H:%M} IST and the merchant's planner reallocates it; "
                                   "a silent expiry is recorded separately from an early, honest partial."
                                   if alloc.confirmation_expires_at else ""),
        "basis": "Deterministic rules over recorded stock, commitments and capacity. Not a predictive model.",
    }


# ------------------------------------------------------------------- drift / risk

def assess_commitment(db: Session, supplier: SupplierProfile, a: Allocation, pos: InventoryPosition | None,
                      history: dict | None = None) -> dict:
    """Rule-based risk that a live commitment will not be met. Every point is listed."""
    now = now_utc()
    factors: list[dict] = []
    stage = stage_of(a)
    if pos is not None:
        if pos.freshness["status"] == "stale":
            factors.append({"factor": "stale_stock", "points": 2, "at": pos.freshness["confirmed_at"],
                            "detail": f"Stock not counted for {pos.freshness['age_hours']}h"})
        if pos.drift_qty > EPS:
            factors.append({"factor": "count_below_commitments", "points": 3, "at": pos.inventory.stock_confirmed_at,
                            "detail": f"Last count {pos.inventory.reported_on_hand_base_unit:g} is {pos.drift_qty:g} below live commitments"})
    if a.confirmed_ready_by is not None and stage in WAREHOUSE_STAGES:
        hours_left = (a.confirmed_ready_by - now).total_seconds() / 3600
        if hours_left < 0:
            factors.append({"factor": "past_ready_by", "points": 3, "at": a.confirmed_ready_by,
                            "detail": f"Ready-by passed {abs(hours_left):.1f}h ago; stage is still {stage}"})
        elif hours_left <= 2 and stage == "reserved":
            factors.append({"factor": "deadline_near_not_picking", "points": 2, "at": a.confirmed_ready_by,
                            "detail": f"Due in {hours_left:.1f}h and picking has not started"})
        elif hours_left <= 6 and stage == "reserved":
            factors.append({"factor": "deadline_approaching", "points": 1, "at": a.confirmed_ready_by,
                            "detail": f"Due in {hours_left:.1f}h"})
        if a.product.base_unit == "kg":
            day = a.confirmed_ready_by.astimezone(IST).date()
            load = day_load(db, supplier.id, day)
            cap = supplier.delivery_capacity_kg_per_day
            if load > cap + EPS:
                factors.append({"factor": "capacity_overload", "points": 2, "at": None,
                                "detail": f"{load:g} kg due {day:%d %b} vs {cap:g} kg/day capacity"})
            elif load > 0.85 * cap:
                factors.append({"factor": "capacity_tight", "points": 1, "at": None,
                                "detail": f"{load:g} kg due {day:%d %b} is {load / cap:.0%} of daily capacity"})
    elif a.confirmed_ready_by is None and stage in WAREHOUSE_STAGES:
        factors.append({"factor": "no_ready_by", "points": 1, "at": None, "detail": "No ready-by time recorded"})
    if history and history.get("broken_rate") is not None and history["broken_rate"] >= 0.2:
        factors.append({"factor": "history_of_broken_commitments", "points": 1, "at": None,
                        "detail": f"{history['broken_rate']:.0%} of past commitments were broken after acceptance"})
    score = sum(f["points"] for f in factors)
    level = "on_track" if score == 0 else "watch" if score <= 2 else "at_risk" if score <= 4 else "critical"
    if pos is None or pos.inventory.stock_confirmed_at is None:
        confidence = "low"
    elif pos.freshness["status"] == "fresh" and a.confirmed_ready_by is not None:
        confidence = "high"
    else:
        confidence = "medium"
    return {"level": level, "score": score, "factors": factors, "confidence": confidence,
            "confidence_basis": "Evidence completeness (fresh stock count, recorded ready-by), not model accuracy.",
            "method": "rule_based_points"}
