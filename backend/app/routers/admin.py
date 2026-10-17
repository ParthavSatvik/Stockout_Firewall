from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.catalog import Product
from app.models.core import MerchantProfile, SupplierProfile, User
from app.models.ops import SupplierReliabilityStat
from app.models.orders import Allocation, AllocationPlan, AllocationStatus, Order, OrderStatus, SupplierEvent
from app.services.reliability import get_or_default_reliability

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/metrics")
def control_tower_metrics(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> dict:
    total_orders = db.query(func.count(Order.id)).scalar() or 0
    by_status = dict(
        db.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    )
    by_status = {k.value: v for k, v in by_status.items()}

    replans = db.query(func.count(AllocationPlan.id)).filter(AllocationPlan.replan_reason != "initial").scalar() or 0
    infeasible_plans = db.query(func.count(AllocationPlan.id)).filter(AllocationPlan.is_feasible.is_(False)).scalar() or 0

    supplier_count = db.query(func.count(SupplierProfile.id)).scalar() or 0
    reliability_rows = db.query(SupplierReliabilityStat).all()
    avg_reliability = (
        round(sum(r.reliability_score for r in reliability_rows) / len(reliability_rows), 3)
        if reliability_rows else None
    )

    return {
        "total_orders": total_orders,
        "orders_by_status": by_status,
        "total_replans": replans,
        "infeasible_plans": infeasible_plans,
        "supplier_count": supplier_count,
        "average_supplier_reliability": avg_reliability,
        "fulfilled_or_partial": by_status.get(OrderStatus.FULFILLED.value, 0) + by_status.get(OrderStatus.PARTIALLY_FULFILLED.value, 0),
    }


@router.get("/suppliers")
def network_suppliers(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[dict]:
    """Supplier network snapshot for the control-tower visualization: real lat/lng,
    real reliability (sample-size aware), and a live count of currently-active
    (non-terminal) allocations -- not a fabricated "load" figure."""
    suppliers = db.query(SupplierProfile).all()
    out = []
    for s in suppliers:
        stat = get_or_default_reliability(db, s.id)
        active_allocations = (
            db.query(func.count(Allocation.id)).join(AllocationPlan, Allocation.plan_id == AllocationPlan.id)
            .filter(AllocationPlan.is_selected.is_(True),
                Allocation.supplier_id == s.id,
                Allocation.status.in_([AllocationStatus.PROPOSED, AllocationStatus.CONFIRMED, AllocationStatus.SHORT_SUPPLY]),
            )
            .scalar() or 0
        )
        out.append({
            "id": s.id, "business_name": s.business_name, "city": s.city,
            "latitude": s.latitude, "longitude": s.longitude, "is_active": s.is_active,
            "reliability_score": stat.reliability_score, "reliability_confidence": stat.confidence,
            "sample_size": stat.sample_size, "active_allocations": active_allocations,
        })
    return out


@router.get("/events")
def recent_events(db: Session = Depends(get_db), _admin: User = Depends(require_admin), limit: int = 30) -> list[dict]:
    """Recent SupplierEvent entries network-wide -- the real audit trail driving every
    replan, not a decorative activity feed."""
    rows = (
        db.query(SupplierEvent, Allocation, SupplierProfile, Product)
        .join(Allocation, SupplierEvent.allocation_id == Allocation.id)
        .join(SupplierProfile, Allocation.supplier_id == SupplierProfile.id)
        .join(Product, Allocation.product_id == Product.id)
        .order_by(SupplierEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": ev.id, "event_type": ev.event_type.value, "created_at": ev.created_at.isoformat(),
            "supplier_name": supplier.business_name, "product_name": product.name,
            "allocation_id": alloc.id, "order_id": alloc.plan.order_id, "triggered_replan": ev.triggered_replan,
        }
        for ev, alloc, supplier, product in rows
    ]


@router.get("/merchants")
def network_merchants(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[dict]:
    merchants = db.query(MerchantProfile).all()
    return [
        {"id": m.id, "business_name": m.business_name, "city": m.city, "latitude": m.latitude, "longitude": m.longitude}
        for m in merchants
    ]
