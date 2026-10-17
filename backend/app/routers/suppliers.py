from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_supplier_profile
from app.models.catalog import PriceObservation, Product, SupplierInventory
from app.models.core import SupplierProfile
from app.models.orders import Allocation, AllocationPlan, OrderItem
from app.schemas.catalog import InventoryUpsertRequest, SupplierInventoryRead
from app.schemas.orders import AllocationRead
from app.services.reliability import get_or_default_reliability, recompute_supplier_reliability

router = APIRouter(prefix="/api/suppliers/me", tags=["suppliers"])


@router.get("/inventory", response_model=list[SupplierInventoryRead])
def my_inventory(
    db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)
) -> list[SupplierInventoryRead]:
    rows = db.query(SupplierInventory, Product).join(Product, SupplierInventory.product_id == Product.id).filter(
        SupplierInventory.supplier_id == supplier.id
    ).all()
    stat = get_or_default_reliability(db, supplier.id)
    return [
        SupplierInventoryRead(
            id=inv.id, supplier_id=supplier.id, supplier_name=supplier.business_name,
            product_id=p.id, product_name=p.name, brand=inv.brand, pack_size=inv.pack_size,
            pack_unit=inv.pack_unit, price_per_base_unit=inv.price_per_base_unit,
            stock_qty_base_unit=inv.stock_qty_base_unit, moq_base_unit=inv.moq_base_unit,
            is_available=inv.is_available, freshness_source=inv.freshness_source,
            reliability_score=stat.reliability_score, reliability_confidence=stat.confidence,
            reliability_sample_size=stat.sample_size,
        )
        for inv, p in rows
    ]


@router.post("/inventory", response_model=SupplierInventoryRead, status_code=status.HTTP_201_CREATED)
def upsert_inventory(
    payload: InventoryUpsertRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> SupplierInventoryRead:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    if payload.pack_unit != product.base_unit:
        raise HTTPException(422, "Pack unit must match canonical product unit")

    inv = (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier.id, SupplierInventory.product_id == payload.product_id,
                SupplierInventory.brand == payload.brand, SupplierInventory.pack_size == payload.pack_size)
        .first()
    )
    if inv is None:
        inv = SupplierInventory(supplier_id=supplier.id, product_id=payload.product_id)
        db.add(inv)

    inv.brand = payload.brand
    inv.pack_size = payload.pack_size
    inv.pack_unit = payload.pack_unit
    inv.price_per_base_unit = payload.price_per_base_unit
    inv.stock_qty_base_unit = payload.stock_qty_base_unit
    inv.moq_base_unit = payload.moq_base_unit
    inv.is_available = payload.is_available
    inv.freshness_source = "manual"
    db.add(PriceObservation(supplier_id=supplier.id, product_id=payload.product_id, price_per_base_unit=payload.price_per_base_unit))
    db.commit()
    db.refresh(inv)

    stat = get_or_default_reliability(db, supplier.id)
    return SupplierInventoryRead(
        id=inv.id, supplier_id=supplier.id, supplier_name=supplier.business_name,
        product_id=product.id, product_name=product.name, brand=inv.brand, pack_size=inv.pack_size,
        pack_unit=inv.pack_unit, price_per_base_unit=inv.price_per_base_unit,
        stock_qty_base_unit=inv.stock_qty_base_unit, moq_base_unit=inv.moq_base_unit,
        is_available=inv.is_available, freshness_source=inv.freshness_source,
        reliability_score=stat.reliability_score, reliability_confidence=stat.confidence,
        reliability_sample_size=stat.sample_size,
    )


@router.get("/allocations", response_model=list[AllocationRead])
def incoming_allocations(
    db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)
) -> list[AllocationRead]:
    """Incoming order review queue for this supplier -- accept/modify/reject happens
    via the /api/allocations/{id}/... endpoints. Only allocations on the order's
    currently *selected* plan are shown: a merchant may have generated cheapest/
    fastest/most-reliable alternatives that also proposed this supplier, but those
    sibling plans are not live until the merchant selects them."""
    rows = (
        db.query(Allocation, OrderItem, Product)
        .join(OrderItem, Allocation.order_item_id == OrderItem.id)
        .join(Product, Allocation.product_id == Product.id)
        .join(AllocationPlan, Allocation.plan_id == AllocationPlan.id)
        .filter(Allocation.supplier_id == supplier.id, AllocationPlan.is_selected.is_(True))
        .order_by(Allocation.created_at.desc())
        .all()
    )
    return [
        AllocationRead(
            id=a.id, plan_id=a.plan_id, order_item_id=oi.id, supplier_id=supplier.id,
            supplier_name=supplier.business_name, product_id=p.id, product_name=p.name,
            allocated_qty_base_unit=a.allocated_qty_base_unit, unit_price=a.unit_price,
            pack_count=a.pack_count, status=a.status, confirmed_qty_base_unit=a.confirmed_qty_base_unit,
            confirmed_ready_by=a.confirmed_ready_by, confirmation_expires_at=a.confirmation_expires_at,
            route_distance_km=a.route_distance_km, route_duration_minutes=a.route_duration_minutes,
            route_source=a.route_source, route_cost=a.route_cost,
        )
        for a, oi, p in rows
    ]


@router.get("/reliability")
def my_reliability(
    db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)
) -> dict:
    stat = recompute_supplier_reliability(db, supplier.id)
    db.commit()
    return {
        "supplier_id": supplier.id,
        "reliability_score": stat.reliability_score,
        "confidence": stat.confidence,
        "sample_size": stat.sample_size,
        "total_commitments": stat.total_commitments,
        "fulfilled_count": stat.fulfilled_count,
        "short_supply_count": stat.short_supply_count,
        "rejected_count": stat.rejected_count,
        "expired_count": stat.expired_count,
    }
