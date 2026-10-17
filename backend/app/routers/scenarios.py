from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile
from app.models.core import MerchantProfile
from app.models.orders import (
    Allocation,
    AllocationPlan,
    AllocationStatus,
    Order,
    SupplierEvent,
    SupplierEventType,
)
from app.schemas.scenarios import ScenarioDisruptionRequest, ScenarioResultResponse
from app.services.planning import replan_after_event

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.post("/disrupt", response_model=ScenarioResultResponse)
def apply_disruption(
    payload: ScenarioDisruptionRequest, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> ScenarioResultResponse:
    """Supply Chain Digital Twin control. Reuses the exact same failover/replan engine
    that a real supplier-reported event uses -- this is not a separate fake code path."""
    from app.config import get_settings
    if not get_settings().demo_mode:
        raise HTTPException(403, "Disruption simulation is demo-only")
    order = db.get(Order, payload.order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    alloc = db.get(Allocation, payload.allocation_id)
    if alloc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Allocation not found")
    plan = db.get(AllocationPlan, alloc.plan_id)
    if plan.order_id != order.id or not plan.is_selected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Allocation is not on the order's active plan")
    if alloc.status != AllocationStatus.CONFIRMED and alloc.status != AllocationStatus.PROPOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot disrupt a {alloc.status.value} allocation")

    before_plan = plan
    before_total_cost = before_plan.total_cost
    before_hours = before_plan.estimated_delivery_hours

    if payload.disruption_type == "supplier_outage":
        alloc.status = AllocationStatus.REJECTED
        alloc.confirmed_qty_base_unit = 0.0
        event_type = SupplierEventType.DISRUPTED
        narrative = f"Simulated outage at {alloc.supplier_id}: allocation rejected, system reallocates."
    elif payload.disruption_type == "partial_stock":
        remaining_pct = max(0.0, 1 - payload.magnitude_pct / 100.0)
        alloc.status = AllocationStatus.SHORT_SUPPLY
        alloc.confirmed_qty_base_unit = round(alloc.allocated_qty_base_unit * remaining_pct, 3)
        event_type = SupplierEventType.DISRUPTED
        narrative = (
            f"Simulated partial stock disruption: only {alloc.confirmed_qty_base_unit} of "
            f"{alloc.allocated_qty_base_unit} now deliverable."
        )
    elif payload.disruption_type == "delivery_delay":
        alloc.route_duration_minutes = (alloc.route_duration_minutes or 0) * (1 + payload.magnitude_pct / 100.0)
        from app.services.planning import recompute_plan_totals
        recompute_plan_totals(db, plan)
        db.commit()
        return ScenarioResultResponse(
            order_id=order.id, disruption_type=payload.disruption_type, before_plan_id=plan.id,
            after_plan_id=plan.id, before_total_cost=before_total_cost, after_total_cost=plan.total_cost,
            before_delivery_hours=before_hours, after_delivery_hours=round((alloc.route_duration_minutes or 0) / 60, 2),
            narrative=f"Simulated delivery delay of +{payload.magnitude_pct:.0f}% on allocation {alloc.id}.",
        )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown disruption_type: {payload.disruption_type}")

    db.add(SupplierEvent(
        allocation_id=alloc.id, event_type=event_type,
        payload={"scenario": True, "disruption_type": payload.disruption_type, "description": payload.description},
        triggered_replan=True,
    ))
    db.flush()
    new_plan = replan_after_event(db, order, alloc, reason=f"digital_twin:{payload.disruption_type}")
    db.commit()
    db.refresh(new_plan)

    return ScenarioResultResponse(
        order_id=order.id, disruption_type=payload.disruption_type, before_plan_id=before_plan.id,
        after_plan_id=new_plan.id, before_total_cost=before_total_cost, after_total_cost=new_plan.total_cost,
        before_delivery_hours=before_hours, after_delivery_hours=new_plan.estimated_delivery_hours,
        narrative=narrative,
    )
