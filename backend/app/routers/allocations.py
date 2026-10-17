from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_supplier_profile
from app.models.catalog import SupplierInventory
from app.models.core import SupplierProfile
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
)
from app.services.planning import replan_after_event, sync_order_status
from app.services.reliability import recompute_supplier_reliability

router = APIRouter(prefix="/api/allocations", tags=["allocations"])


def _load_owned_allocation(db: Session, allocation_id: str, supplier: SupplierProfile) -> tuple[Allocation, Order]:
    alloc = db.get(Allocation, allocation_id)
    if alloc is None or alloc.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    plan = db.get(AllocationPlan, alloc.plan_id)
    order = db.get(Order, plan.order_id)
    if not plan.is_selected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Allocation belongs to a superseded plan")
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
        route_source=alloc.route_source, route_cost=alloc.route_cost,
    )


@router.post("/{allocation_id}/confirm", response_model=AllocationRead)
def confirm_allocation(
    allocation_id: str, payload: AllocationConfirmRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> AllocationRead:
    alloc, order = _load_owned_allocation(db, allocation_id, supplier)

    if payload.confirmed_qty_base_unit > alloc.allocated_qty_base_unit + 1e-6:
        raise HTTPException(422, "Confirmation exceeds allocation")
    if alloc.inventory_id is None:
        raise HTTPException(409, "Legacy allocation has no inventory reference; create a new order")
    changed = db.execute(update(SupplierInventory).where(
        SupplierInventory.id == alloc.inventory_id,
        SupplierInventory.is_available.is_(True),
        SupplierInventory.stock_qty_base_unit >= payload.confirmed_qty_base_unit,
    ).values(stock_qty_base_unit=SupplierInventory.stock_qty_base_unit - payload.confirmed_qty_base_unit))
    if changed.rowcount != 1:
        raise HTTPException(409, "Stock changed; report a shortfall or reject this proposal")

    if payload.confirmed_qty_base_unit >= alloc.allocated_qty_base_unit - 1e-6:
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

    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=event_type,
        payload={"confirmed_qty_base_unit": payload.confirmed_qty_base_unit}, triggered_replan=triggers_replan,
    ))
    from app.models.catalog import PriceObservation
    db.add(PriceObservation(supplier_id=alloc.supplier_id, product_id=alloc.product_id, price_per_base_unit=alloc.unit_price))
    db.flush()

    if triggers_replan:
        replan_after_event(db, order, alloc, reason="short_supply")
    else:
        sync_order_status(db, order)

    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    db.refresh(alloc)
    from app.models.catalog import Product
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)


@router.post("/{allocation_id}/reject", response_model=AllocationRead)
def reject_allocation(
    allocation_id: str, payload: AllocationRejectRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> AllocationRead:
    alloc, order = _load_owned_allocation(db, allocation_id, supplier)
    alloc.status = AllocationStatus.REJECTED
    alloc.confirmed_qty_base_unit = 0.0
    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=SupplierEventType.REJECTED,
        payload={"reason": payload.reason}, triggered_replan=True,
    ))
    db.flush()
    replan_after_event(db, order, alloc, reason="rejected")
    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    db.refresh(alloc)
    from app.models.catalog import Product
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)


@router.post("/{allocation_id}/report-shortfall", response_model=AllocationRead)
def report_shortfall(
    allocation_id: str, payload: AllocationShortfallRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> AllocationRead:
    """For a *previously confirmed* allocation that the supplier can no longer fully
    honour (post-confirmation disruption)."""
    alloc = db.get(Allocation, allocation_id)
    if alloc is None or alloc.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    if not alloc.plan.is_selected:
        raise HTTPException(409, "Allocation belongs to a superseded plan")
    if alloc.status not in (AllocationStatus.CONFIRMED,):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot report shortfall on a {alloc.status.value} allocation")
    plan = db.get(AllocationPlan, alloc.plan_id)
    order = db.get(Order, plan.order_id)

    if payload.actual_deliverable_qty_base_unit >= (alloc.confirmed_qty_base_unit or alloc.allocated_qty_base_unit):
        raise HTTPException(422, "Shortfall quantity must be below the commitment")
    alloc.status = AllocationStatus.SHORT_SUPPLY
    alloc.confirmed_qty_base_unit = payload.actual_deliverable_qty_base_unit
    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=SupplierEventType.DISRUPTED,
        payload={"reason": payload.reason, "actual_qty": payload.actual_deliverable_qty_base_unit},
        triggered_replan=True,
    ))
    db.flush()
    replan_after_event(db, order, alloc, reason="post_confirmation_disruption")
    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    db.refresh(alloc)
    from app.models.catalog import Product
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)


@router.post("/{allocation_id}/dispatch", response_model=AllocationRead)
def dispatch_allocation(
    allocation_id: str, db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)
) -> AllocationRead:
    alloc = db.get(Allocation, allocation_id)
    if alloc is None or alloc.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    if not alloc.plan.is_selected:
        raise HTTPException(409, "Allocation belongs to a superseded plan")
    if alloc.status not in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed (or partially confirmed) allocations can be dispatched")
    if not db.query(SupplierEvent).filter(SupplierEvent.allocation_id == alloc.id, SupplierEvent.event_type == SupplierEventType.DISPATCHED).first():
        db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DISPATCHED, payload={}))
    db.commit()
    db.refresh(alloc)
    from app.models.catalog import Product
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)


@router.post("/{allocation_id}/deliver", response_model=AllocationRead)
def deliver_allocation(
    allocation_id: str, db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)
) -> AllocationRead:
    alloc = db.get(Allocation, allocation_id)
    if alloc is None or alloc.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    if not alloc.plan.is_selected:
        raise HTTPException(409, "Allocation belongs to a superseded plan")
    if alloc.status not in (AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed (or partially confirmed) allocations can be marked delivered")
    # A SHORT_SUPPLY line's confirmed partial quantity still has to be physically
    # delivered; marking it FULFILLED here closes that line (its shortfall was already
    # handed off to a replan, so this is not re-claiming the missing quantity).
    alloc.status = AllocationStatus.FULFILLED
    db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DELIVERED, payload={}))
    db.flush()

    plan = db.get(AllocationPlan, alloc.plan_id)
    order = db.get(Order, plan.order_id)
    sync_order_status(db, order)

    recompute_supplier_reliability(db, supplier.id)
    db.commit()
    db.refresh(alloc)
    from app.models.catalog import Product
    product = db.get(Product, alloc.product_id)
    return _to_read(alloc, supplier.business_name, product.name if product else alloc.product_id)
