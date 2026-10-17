import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile
from app.models.core import MerchantProfile
from app.models.ops import Payment, PaymentStatus
from app.models.ops import PaymentProvider as PaymentProviderEnum
from app.models.orders import Order
from app.providers.payments import get_payment_provider
from app.schemas.payments import PaymentInitiateRequest, PaymentRead
from app.services.planning import get_selected_plan

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/initiate", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def initiate_payment(
    payload: PaymentInitiateRequest, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> Payment:
    order = db.get(Order, payload.order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    plan = get_selected_plan(order)
    if plan is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order has no selected plan to pay for")

    existing = db.query(Payment).filter(Payment.order_id == order.id, Payment.status == PaymentStatus.SUCCESS).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order already has a successful payment")

    from app.config import get_settings
    settings = get_settings()
    if settings.razorpay_configured:
        raise HTTPException(409, "Razorpay is configured; pay through /api/payments/razorpay/order and Checkout")
    if not settings.demo_mode:
        raise HTTPException(503, "No verified payment provider is configured")
    provider = get_payment_provider()
    is_simulated = not hasattr(provider, "mid")
    idempotency_key = f"{order.id}:{uuid.uuid4().hex[:8]}"
    result = provider.initiate(order.id, plan.total_cost, merchant.user_id)

    payment = Payment(
        order_id=order.id,
        provider=PaymentProviderEnum.SIMULATED if is_simulated else PaymentProviderEnum.PAYTM,
        amount=plan.total_cost,
        status=PaymentStatus.SUCCESS if result.status == "success" else (
            PaymentStatus.FAILED if result.status == "failed" else PaymentStatus.PENDING
        ),
        provider_order_id=result.provider_order_id,
        provider_txn_id=result.provider_txn_id,
        idempotency_key=idempotency_key,
        raw_provider_response=result.raw_response,
        is_simulated=result.is_simulated,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(
    payment_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    order = db.get(Order, payment.order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


@router.post("/paytm/callback")
async def paytm_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    """Server-side webhook handler. The browser redirect/callback is never trusted by
    itself -- status must be (re-)verified against Paytm's Transaction Status API.
    Signature verification uses the same checksum algorithm as the initiate call.
    """
    raise HTTPException(503, "Provider callbacks disabled pending signature verification")
    form = await request.form()
    order_id = form.get("ORDERID")
    payment = db.query(Payment).filter(Payment.provider_order_id == order_id).first() if order_id else None
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown order")

    from app.config import get_settings
    settings = get_settings()
    if settings.razorpay_configured:
        raise HTTPException(409, "Razorpay is configured; pay through /api/payments/razorpay/order and Checkout")
    if not settings.demo_mode:
        raise HTTPException(503, "No verified payment provider is configured")
    provider = get_payment_provider()
    verified_status = provider.verify_status(payment.provider_order_id)
    payment.status = {
        "success": PaymentStatus.SUCCESS, "failed": PaymentStatus.FAILED, "pending": PaymentStatus.PENDING,
    }[verified_status]
    db.commit()
    return {"ok": True, "status": payment.status.value}
