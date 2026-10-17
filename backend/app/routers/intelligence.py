from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile
from app.models.catalog import MerchantProductPrice, Product
from app.models.core import MerchantProfile
from app.schemas.intelligence import (
    CashCycleInputRequest,
    SellingPriceUpsertRequest,
    SurvivalModeRequest,
)
from app.services import dashboard, intelligence
from app.services.planning import plan_survival_basket

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/dashboard-summary")
def dashboard_summary(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    summary = dashboard.merchant_summary(db, merchant.id)
    return {
        "total_spend": summary.total_spend,
        "estimated_savings": summary.estimated_savings,
        "savings_basis": summary.savings_basis,
        "orders_in_progress": summary.orders_in_progress,
        "orders_awaiting_confirmation": summary.orders_awaiting_confirmation,
        "shortage_alert_count": summary.shortage_alert_count,
        "avg_supplier_reliability": summary.avg_supplier_reliability,
        "recent_recovery_events": summary.recent_recovery_events,
        "action_feed": [asdict(a) for a in summary.action_feed],
    }


@router.get("/stockout-radar")
def get_stockout_radar(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    return [asdict(r) for r in intelligence.stockout_radar(db, merchant.id)]


@router.post("/survival-mode")
def survival_mode(
    payload: SurvivalModeRequest, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> dict:
    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one item is required")
    ids = [i.product_id for i in payload.items]
    if len(ids) != len(set(ids)) or db.query(Product).filter(Product.id.in_(ids)).count() != len(ids):
        raise HTTPException(422, "Use unique, valid products")
    return plan_survival_basket(
        db, merchant.latitude, merchant.longitude,
        [item.model_dump() for item in payload.items],
        payload.budget_cap, payload.price_tolerance_pct, payload.min_reliability, payload.max_suppliers,
    )


@router.get("/cash-cycle")
def get_cash_cycle(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    return asdict(intelligence.cash_cycle_summary(db, merchant.id, merchant.available_cash_on_hand))


@router.post("/cash-cycle/cash-on-hand")
def set_cash_on_hand(
    payload: CashCycleInputRequest, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> dict:
    merchant.available_cash_on_hand = payload.available_cash_on_hand
    db.commit()
    return asdict(intelligence.cash_cycle_summary(db, merchant.id, merchant.available_cash_on_hand))


@router.get("/margin-leak")
def get_margin_leak(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    return [asdict(r) for r in intelligence.margin_leak_report(db, merchant.id)]


@router.get("/selling-prices")
def list_selling_prices(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    rows = db.query(MerchantProductPrice, Product).join(Product, MerchantProductPrice.product_id == Product.id).filter(
        MerchantProductPrice.merchant_id == merchant.id
    ).all()
    return [
        {"id": mpp.id, "product_id": p.id, "product_name": p.name, "selling_price_per_base_unit": mpp.selling_price_per_base_unit}
        for mpp, p in rows
    ]


@router.post("/selling-prices", status_code=status.HTTP_201_CREATED)
def upsert_selling_price(
    payload: SellingPriceUpsertRequest, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> dict:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    row = db.query(MerchantProductPrice).filter(
        MerchantProductPrice.merchant_id == merchant.id, MerchantProductPrice.product_id == payload.product_id
    ).first()
    if row is None:
        row = MerchantProductPrice(merchant_id=merchant.id, product_id=payload.product_id)
        db.add(row)
    row.selling_price_per_base_unit = payload.selling_price_per_base_unit
    db.commit()
    return {"id": row.id, "product_id": product.id, "product_name": product.name, "selling_price_per_base_unit": row.selling_price_per_base_unit}


@router.get("/price-index")
def get_price_index(
    product_id: str = Query(...), db: Session = Depends(get_db), _merchant: MerchantProfile = Depends(get_merchant_profile)
) -> dict:
    return asdict(intelligence.price_index(db, product_id))


@router.get("/autopilot-suggestions")
def get_autopilot_suggestions(db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    return [asdict(s) for s in intelligence.autopilot_suggestions(db, merchant.id)]
