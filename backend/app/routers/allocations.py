from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_supplier_profile
from app.models.catalog import PriceObservation, Product, SupplierInventory
from app.models.core import SupplierProfile, User
from app.models.orders import (
    Allocation,
    AllocationPlan,
    AllocationStatus,
    Order,
    SupplierEvent,
    SupplierEventType,
)
from app.schemas.orders import (
    AllocationConfirmRequest,
    AllocationRead,
    AllocationRejectRequest,
    AllocationShortfallRequest,
    RelayOpenRequest,
    StageUpdateRequest,
)
from app.security import get_current_user
from app.services import relay as relay_service
from app.services.planning import replan_after_event, sync_order_status
from app.services.promise import EPS, STAGES, assess_request, log, now_utc, position_for, reserve_stock, stage_of
from app.services.reliability import recompute_supplier_reliability

router = APIRouter(prefix="/api/allocations", tags=["allocations"])


def _owned(db: Session, allocation_id: str, supplier: SupplierProfile) -> tuple[Allocation, Order]:
    alloc = db.get(Allocation, allocation_id)
    if alloc is None or alloc.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    plan = db.get(AllocationPlan, alloc.plan_id)
    if not plan.is_selected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Allocation belongs to a superseded plan")
    return alloc, db.get(Order, plan.order_id)


def _load_owned_allocation(db: Session, allocation_id: str, supplier: SupplierProfile) -> tuple[Allocation, Order]:
    alloc, order = _owned(db, allocation_id, supplier)
    if alloc.status != AllocationStatus.PROPOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Allocation is already {alloc.status.value}")
    return alloc, order


def _to_read(alloc: Allocation, supplier_name: str, product_name: str) -> AllocationRead:
    return AllocationRead(
        id=alloc.id, plan_id=alloc.plan_id, order_item_id=alloc.order_item_id, supplier_id=alloc.supplier_id,
        supplier_name=supplier_name, product_id=alloc.product_id, product_name=product_name,
        allocated_qty_base_unit=alloc.allocated_qty_base_unit, unit_price=alloc.unit_price,
        pack_count=alloc.pack_count, status=alloc.status, confirmed_qty_base_unit=alloc.confirmed_qty_base_unit,
        confirmed_ready_by=alloc.confirmed_ready_by, confirmation_expires_at=alloc.confirmation_expires_at,
        route_distance_km=alloc.route_distance_km, route_duration_minutes=alloc.route_duration_minutes,
        route_source=alloc.route_source, route_cost=alloc.route_cost, fulfillment_stage=alloc.fulfillment_stage,
    )


def _read(db: Session, alloc: Allocation, supplier: SupplierProfile) -> AllocationRead:
    db.refresh(alloc)
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)


@router.get("/{allocation_id}/guard")
def promise_guard(
    allocation_id: str, ready_by: datetime | None = Query(default=None), db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> dict:
    """PromiseGuard pre-commitment assessment. Read-only: nothing is reserved."""
    alloc, _ = _load_owned_allocation(db, allocation_id, supplier)
    return assess_request(db, supplier, alloc, ready_by)


@router.post("/{allocation_id}/confirm", response_model=AllocationRead)
def confirm_allocation(
    allocation_id: str, payload: AllocationConfirmRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> AllocationRead:
    alloc, order = _load_owned_allocation(db, allocation_id, supplier)

    if payload.confirmed_qty_base_unit > alloc.allocated_qty_base_unit + EPS:
        raise HTTPException(422, "Confirmation exceeds allocation")
    if payload.ready_by <= now_utc():
        raise HTTPException(422, "Ready-by must be in the future")
    if alloc.inventory_id is None:
        raise HTTPException(409, "Legacy allocation has no inventory reference; create a new order")
    if payload.override_safety_stock and len(payload.override_reason.strip()) < 3:
        raise HTTPException(422, "Explain why safety stock is being used")
    inv = db.get(SupplierInventory, alloc.inventory_id)
    if inv.product_id != alloc.product_id or inv.pack_unit != alloc.product.base_unit:
        raise HTTPException(409, "Inventory record does not match the requested product or unit")
    if not reserve_stock(db, alloc.inventory_id, payload.confirmed_qty_base_unit, allow_safety_stock=payload.override_safety_stock):
        pos = position_for(db, inv)
        raise HTTPException(409, f"Stock changed: only {pos.free_to_promise:g} {alloc.product.base_unit} is free to promise "
                                 f"({pos.safety_stock:g} held as safety stock). Commit less, open a relay or reject.")

    if payload.confirmed_qty_base_unit >= alloc.allocated_qty_base_unit - EPS:
        alloc.status = AllocationStatus.CONFIRMED
        alloc.confirmed_qty_base_unit = alloc.allocated_qty_base_unit
        event_type = SupplierEventType.CONFIRMED
        triggers_replan = False
    else:
        # Partial confirmation: e.g. "confirms 40 of 100kg" -- the confirmed amount is
        # kept, the remainder becomes an immediate shortfall that triggers failover.
        alloc.status = AllocationStatus.SHORT_SUPPLY
        alloc.confirmed_qty_base_unit = payload.confirmed_qty_base_unit
        event_type = SupplierEventType.SHORT_SUPPLY
        triggers_replan = True
    alloc.confirmed_ready_by = payload.ready_by
    alloc.fulfillment_stage = "reserved"

    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=event_type,
        payload={"confirmed_qty_base_unit": payload.confirmed_qty_base_unit, "safety_stock_override": payload.override_safety_stock},
        triggered_replan=triggers_replan,
    ))
    log(db, "commitment_accepted" if not triggers_replan else "partial_commitment", actor_user_id=user.id, actor_role="supplier",
        supplier_id=supplier.id, order_id=order.id, allocation_id=alloc.id, inventory_id=alloc.inventory_id,
        from_state="proposed", to_state=alloc.status.value, qty=payload.confirmed_qty_base_unit,
        reason=payload.override_reason if payload.override_safety_stock else "",
        payload={"requested": alloc.allocated_qty_base_unit, "unit_price": alloc.unit_price,
                 "ready_by": payload.ready_by.isoformat(), "safety_stock_override": payload.override_safety_stock})
    db.add(PriceObservation(supplier_id=alloc.supplier_id, product_id=alloc.product_id, price_per_base_unit=alloc.unit_price))
    db.flush()

    if triggers_replan:
        replan_after_event(db, order, alloc, reason="short_supply")
    else:
        sync_order_status(db, order)

    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    return _read(db, alloc, supplier)


@router.post("/{allocation_id}/reject", response_model=AllocationRead)
def reject_allocation(
    allocation_id: str, payload: AllocationRejectRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> AllocationRead:
    alloc, order = _load_owned_allocation(db, allocation_id, supplier)
    alloc.status = AllocationStatus.REJECTED
    alloc.confirmed_qty_base_unit = 0.0
    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=SupplierEventType.REJECTED,
        payload={"reason": payload.reason, "reason_code": payload.reason_code}, triggered_replan=True,
    ))
    log(db, "request_rejected", actor_user_id=user.id, actor_role="supplier", supplier_id=supplier.id, order_id=order.id,
        allocation_id=alloc.id, from_state="proposed", to_state="rejected", qty=0.0,
        reason=f"{payload.reason_code}: {payload.reason}".strip(": "))
    db.flush()
    replan_after_event(db, order, alloc, reason="rejected")
    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    return _read(db, alloc, supplier)


@router.post("/{allocation_id}/report-shortfall", response_model=AllocationRead)
def report_shortfall(
    allocation_id: str, payload: AllocationShortfallRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> AllocationRead:
    """For a *previously confirmed* allocation that the supplier can no longer fully
    honour (post-confirmation disruption)."""
    alloc, order = _owned(db, allocation_id, supplier)
    if alloc.status not in (AllocationStatus.CONFIRMED,):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot report shortfall on a {alloc.status.value} allocation")

    if payload.actual_deliverable_qty_base_unit >= (alloc.confirmed_qty_base_unit or alloc.allocated_qty_base_unit):
        raise HTTPException(422, "Shortfall quantity must be below the commitment")
    previous_qty = alloc.confirmed_qty_base_unit
    alloc.status = AllocationStatus.SHORT_SUPPLY
    alloc.confirmed_qty_base_unit = payload.actual_deliverable_qty_base_unit
    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=SupplierEventType.DISRUPTED,
        payload={"reason": payload.reason, "actual_qty": payload.actual_deliverable_qty_base_unit},
        triggered_replan=True,
    ))
    log(db, "commitment_broken", actor_user_id=user.id, actor_role="supplier", supplier_id=supplier.id, order_id=order.id,
        allocation_id=alloc.id, from_state="confirmed", to_state="short_supply", qty=payload.actual_deliverable_qty_base_unit,
        reason=payload.reason, payload={"previously_committed": previous_qty})
    db.flush()
    replan_after_event(db, order, alloc, reason="post_confirmation_disruption")
    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    return _read(db, alloc, supplier)


def _advance_stage(db: Session, alloc: Allocation, order: Order, supplier: SupplierProfile, user: User, target: str, note: str = "") -> bool:
    """Forward-only stage change. Repeating the current stage is a no-op (idempotent);
    moving backwards is refused."""
    if alloc.status not in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed (or partially confirmed) allocations move through fulfilment")
    if (alloc.confirmed_qty_base_unit or 0) <= EPS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing was committed on this line")
    current = stage_of(alloc)
    if current == target:
        return False
    if STAGES.index(target) < STAGES.index(current):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move from {current} back to {target}")
    alloc.fulfillment_stage = target
    log(db, "stage_changed", actor_user_id=user.id, actor_role="supplier", supplier_id=supplier.id, order_id=order.id,
        allocation_id=alloc.id, inventory_id=alloc.inventory_id, from_state=current, to_state=target,
        qty=alloc.confirmed_qty_base_unit, reason=note)
    return True


@router.post("/{allocation_id}/stage", response_model=AllocationRead)
def update_stage(
    allocation_id: str, payload: StageUpdateRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> AllocationRead:
    alloc, order = _owned(db, allocation_id, supplier)
    _advance_stage(db, alloc, order, supplier, user, payload.stage, payload.note)
    db.commit()
    return _read(db, alloc, supplier)


@router.post("/{allocation_id}/dispatch", response_model=AllocationRead)
def dispatch_allocation(
    allocation_id: str, db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile),
    user: User = Depends(get_current_user),
) -> AllocationRead:
    alloc, order = _owned(db, allocation_id, supplier)
    if _advance_stage(db, alloc, order, supplier, user, "dispatched"):
        db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DISPATCHED, payload={}))
    db.commit()
    return _read(db, alloc, supplier)


@router.post("/{allocation_id}/deliver", response_model=AllocationRead)
def deliver_allocation(
    allocation_id: str, db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile),
    user: User = Depends(get_current_user),
) -> AllocationRead:
    alloc, order = _owned(db, allocation_id, supplier)
    if alloc.status not in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed (or partially confirmed) allocations can be marked delivered")
    # A SHORT_SUPPLY line's confirmed partial quantity still has to be physically
    # delivered; marking it FULFILLED here closes that line (its shortfall was already
    # handed off to a replan, so this is not re-claiming the missing quantity).
    _advance_stage(db, alloc, order, supplier, user, "delivered")
    alloc.status = AllocationStatus.FULFILLED
    db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DELIVERED, payload={}))
    db.flush()
    sync_order_status(db, order)
    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    return _read(db, alloc, supplier)


@router.post("/{allocation_id}/relay", status_code=status.HTTP_201_CREATED)
def open_supply_relay(
    allocation_id: str, payload: RelayOpenRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> dict:
    """Supply Relay Protocol step 1: keep what you can, hand the exact gap to partners."""
    alloc, order = _owned(db, allocation_id, supplier)
    relay = relay_service.open_relay(db, user, supplier, alloc, order, payload.commit_qty_base_unit,
                                     payload.ready_by, payload.reason, payload.response_window_minutes)
    db.commit()
    db.refresh(relay)
    return relay_service.relay_view(db, relay, "origin")
