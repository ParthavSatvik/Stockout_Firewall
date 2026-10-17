from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile
from app.models.core import MerchantProfile
from app.models.orders import Order, OrderItem, OrderStatus
from app.schemas.orders import OrderCreate, OrderRead, PlanComparisonResponse, SelectPlanRequest
from app.services.parsing import parse_order_text
from app.services.planning import create_initial_plans, expire_overdue_allocations, select_plan
from app.services.relay import expire_due_relays

router = APIRouter(prefix="/api/orders", tags=["orders"])

LOW_CONFIDENCE_THRESHOLD = 0.75


class ParseTextRequest(BaseModel):
    text: str = Field(max_length=5000)
    language: str = Field(default="en", max_length=10)


@router.post("/parse-text")
def parse_text(
    payload: ParseTextRequest, db: Session = Depends(get_db),
    _merchant: MerchantProfile = Depends(get_merchant_profile),
) -> dict:
    """Deterministic lexicon extraction first; the Sarvam LLM assists only when that finds
    nothing or is unsure, and its lines always require merchant confirmation."""
    from app.services.order_intake import parse_with_assist
    return parse_with_assist(payload.text, db)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> Order:
    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must contain at least one item")

    from app.models.catalog import Product
    ids = [i.product_id for i in payload.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Combine duplicate products into one order line")
    if db.query(Product).filter(Product.id.in_(ids)).count() != len(ids):
        raise HTTPException(422, "Unknown product")

    parse_confidence = 1.0
    requires_confirmation = False
    if payload.raw_input_text:
        parsed = parse_order_text(payload.raw_input_text, db)
        parse_confidence = parsed.overall_confidence
        requires_confirmation = parse_confidence < LOW_CONFIDENCE_THRESHOLD or bool(parsed.unmatched_fragments)

    order = Order(
        merchant_id=merchant.id,
        status=OrderStatus.DRAFT,
        objective_profile=payload.objective_profile,
        budget_cap=payload.budget_cap,
        price_tolerance_pct=payload.price_tolerance_pct,
        min_reliability=payload.min_reliability,
        allow_substitution=payload.allow_substitution,
        max_suppliers=payload.max_suppliers,
        preferred_supplier_ids=payload.preferred_supplier_ids,
        raw_input_text=payload.raw_input_text,
        raw_input_language=payload.raw_input_language,
        parse_confidence=parse_confidence,
        requires_confirmation=requires_confirmation,
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        db.add(
            OrderItem(
                order_id=order.id, product_id=item.product_id,
                requested_qty_base_unit=item.requested_qty_base_unit,
                substitution_allowed=item.substitution_allowed, notes=item.notes,
            )
        )
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/plan", response_model=PlanComparisonResponse)
def plan_order(
    order_id: str, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> PlanComparisonResponse:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status not in (OrderStatus.DRAFT, OrderStatus.PLANNED):
        raise HTTPException(409, "Cannot regenerate plans after approval")
    if order.requires_confirmation:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Parsed order has low confidence and requires merchant confirmation of items before planning",
        )
    # Regenerating replaces the previous (never-approved) alternatives, so recovery can't
    # later read a stale price ceiling from an older run.
    for old in list(order.plans):
        db.delete(old)
    db.flush()
    db.expire(order, ["plans"])
    plans = create_initial_plans(db, order)
    db.commit()
    for p in plans:
        db.refresh(p)
    db.refresh(order)
    return PlanComparisonResponse(order_id=order.id, plans=plans)


@router.post("/{order_id}/select-plan", response_model=OrderRead)
def choose_plan(
    order_id: str, payload: SelectPlanRequest, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    plan_ids = {p.id for p in order.plans}
    if payload.plan_id not in plan_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown plan for this order")
    selected = next((p for p in order.plans if p.is_selected), None)
    if selected:
        if selected.id == payload.plan_id:
            return order
        raise HTTPException(409, "An approved plan cannot be replaced; use the recovery workflow")
    select_plan(db, order, payload.plan_id)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderRead])
def list_orders(
    db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> list[Order]:
    orders = db.query(Order).filter(Order.merchant_id == merchant.id).order_by(Order.created_at.desc()).all()
    expire_due_relays(db)
    for o in orders:
        expire_overdue_allocations(db, o)
    db.commit()
    return orders


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    expire_due_relays(db, order.id)
    expire_overdue_allocations(db, order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}/evidence")
def order_evidence(order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    from app.services.evidence import recovery_evidence
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(404, "Order not found")
    return recovery_evidence(order)


@router.post("/{order_id}/confirm-items", response_model=OrderRead)
def confirm_reviewed_items(order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(404, "Order not found")
    if order.status != OrderStatus.DRAFT:
        raise HTTPException(409, "Only a draft basket can be reviewed")
    order.requires_confirmation = False
    db.commit()
    db.refresh(order)
    return order
