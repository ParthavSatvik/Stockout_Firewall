"""Live provider integrations wired into the existing order workflow:
Sarvam voice orders, Razorpay checkout, Twilio WhatsApp ordering, OSRM road routes."""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_merchant_profile
from app.models.core import MerchantProfile, SupplierProfile, User, UserRole
from app.models.ops import Payment, PaymentProvider, PaymentStatus, ProviderEvent
from app.models.orders import AllocationStatus, Order, OrderItem, OrderStatus
from app.providers import razorpay, sarvam, whatsapp
from app.routers.orders import LOW_CONFIDENCE_THRESHOLD
from app.security import get_current_user
from app.services.notify import notify
from app.services.parsing import parse_order_text
from app.services.planning import create_initial_plans, get_selected_plan, select_plan

log = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])
MAX_AUDIO_BYTES = 5 * 1024 * 1024


def _record_event(db: Session, provider: str, external_id: str, event_type: str, payload: dict) -> bool:
    """True the first time a provider event id is seen; False for a retry/duplicate."""
    db.add(ProviderEvent(provider=provider, external_id=external_id[:120], event_type=event_type[:60], payload=payload))
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _parse_result(text: str, db: Session) -> dict:
    result = parse_order_text(text, db)
    return {
        "items": [{"matched_text": i.matched_text, "quantity_base_unit": i.quantity_base_unit, "base_unit": i.base_unit,
                   "product_id": i.product_id, "product_name": i.product_name, "matched_alias": i.matched_alias,
                   "confidence": i.confidence} for i in result.items],
        "overall_confidence": result.overall_confidence,
        "unmatched_fragments": result.unmatched_fragments,
        "requires_confirmation": result.overall_confidence < LOW_CONFIDENCE_THRESHOLD or bool(result.unmatched_fragments),
    }


# ------------------------------------------------------------------ status

@router.get("/api/integrations/status")
def integration_status(_user: User = Depends(get_current_user)) -> dict:
    """What is configured. Configured is not the same as verified live; see BUILD_STATUS.md."""
    s = get_settings()
    return {
        "sarvam_stt": s.sarvam_configured, "supabase_auth": s.supabase_configured,
        "razorpay": s.razorpay_mode, "payments_live_enabled": s.payments_live_enabled,
        "twilio_whatsapp": s.twilio_configured, "whatsapp_inbound_verifiable": bool(s.twilio_auth_token and s.public_base_url),
        "routing": "osrm" if s.routing_enabled else "estimated",
    }


# ------------------------------------------------------------- voice orders

@router.post("/api/orders/transcribe")
async def transcribe_order(
    audio: UploadFile = File(...), language_code: str = Form("unknown"), db: Session = Depends(get_db),
    _merchant: MerchantProfile = Depends(get_merchant_profile),
) -> dict:
    """Sarvam speech-to-text, then the same deterministic parser as typed orders."""
    if not get_settings().sarvam_configured:
        raise HTTPException(503, "Voice ordering needs SARVAM_API_KEY; type the order instead")
    data = await audio.read()
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(422, "Audio must be between 1 byte and 5 MB (about 30 seconds)")
    try:
        t = sarvam.transcribe(data, audio.filename or "order.webm", language_code)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sarvam transcription failed: {exc.__class__.__name__}") from exc
    return {"transcript": t.transcript, "language_code": t.language_code, "language_probability": t.language_probability,
            "request_id": t.request_id, "source": "sarvam", "parse": _parse_result(t.transcript, db)}


# ----------------------------------------------------------------- payments

class RazorpayOrderRequest(BaseModel):
    order_id: str


class RazorpayVerifyRequest(BaseModel):
    payment_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/api/payments/config")
def payment_config(_merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    s = get_settings()
    usable = s.razorpay_configured and (s.razorpay_mode == "test" or s.payments_live_enabled)
    return {"provider": "razorpay" if usable else "simulated", "mode": s.razorpay_mode,
            "key_id": s.razorpay_key_id if usable else None}


@router.post("/api/payments/razorpay/order", status_code=status.HTTP_201_CREATED)
def create_razorpay_order(payload: RazorpayOrderRequest, db: Session = Depends(get_db),
                          merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    order = db.get(Order, payload.order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(404, "Order not found")
    plan = get_selected_plan(order)
    if plan is None or plan.total_cost <= 0:
        raise HTTPException(400, "Order has no approved plan to pay for")
    if db.query(Payment).filter(Payment.order_id == order.id, Payment.status == PaymentStatus.SUCCESS).first():
        raise HTTPException(409, "Order already has a successful payment")
    amount = razorpay.to_paise(plan.total_cost)
    # Idempotency: reuse a recent pending Razorpay order for the same amount.
    recent = datetime.now(UTC) - timedelta(minutes=30)
    payment = (db.query(Payment).filter(Payment.order_id == order.id, Payment.provider == PaymentProvider.RAZORPAY,
                                        Payment.status == PaymentStatus.PENDING, Payment.created_at >= recent)
               .order_by(Payment.created_at.desc()).first())
    if payment is None or razorpay.to_paise(payment.amount) != amount:
        try:
            rp = razorpay.create_order(amount, receipt=f"sf-{order.id[:30]}", notes={"order_id": order.id})
        except razorpay.RazorpayError as exc:
            raise HTTPException(503, str(exc)) from exc
        payment = Payment(order_id=order.id, provider=PaymentProvider.RAZORPAY, amount=plan.total_cost, status=PaymentStatus.PENDING,
                          provider_order_id=rp["id"], idempotency_key=f"razorpay:{rp['id']}",
                          raw_provider_response={"order": {k: rp.get(k) for k in ("id", "amount", "currency", "status", "receipt")}},
                          is_simulated=False)
        db.add(payment)
        db.commit()
    return {"payment_id": payment.id, "razorpay_order_id": payment.provider_order_id, "key_id": get_settings().razorpay_key_id,
            "amount": amount, "currency": "INR", "name": "Stockout Firewall", "description": f"Order #{order.id[:8]}",
            "mode": get_settings().razorpay_mode}


def _mark_paid(db: Session, payment: Payment, razorpay_payment_id: str, source: str) -> None:
    if payment.status == PaymentStatus.SUCCESS:
        return
    payment.status = PaymentStatus.SUCCESS
    payment.provider_txn_id = razorpay_payment_id
    payment.raw_provider_response = {**(payment.raw_provider_response or {}), "confirmed_by": source}
    order = db.get(Order, payment.order_id)
    merchant = db.get(MerchantProfile, order.merchant_id)
    notify(db, merchant.user_id, "payment", "Payment received",
           f"Order #{order.id[:8]}: payment of Rs.{payment.amount:,.2f} confirmed by Razorpay ({get_settings().razorpay_mode} mode).", order.id)


@router.post("/api/payments/razorpay/verify")
def verify_razorpay_payment(payload: RazorpayVerifyRequest, db: Session = Depends(get_db),
                            merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    payment = db.get(Payment, payload.payment_id)
    order = db.get(Order, payment.order_id) if payment else None
    if payment is None or order is None or order.merchant_id != merchant.id or payment.provider != PaymentProvider.RAZORPAY:
        raise HTTPException(404, "Payment not found")
    # The signature is checked against OUR stored order id, never the browser-supplied one.
    if payload.razorpay_order_id != payment.provider_order_id or not razorpay.verify_payment_signature(
            payment.provider_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        log.warning("Razorpay signature mismatch for payment %s", payment.id)
        raise HTTPException(400, "Payment signature could not be verified; the payment is not marked as paid")
    _mark_paid(db, payment, payload.razorpay_payment_id, "checkout_signature")
    db.commit()
    return {"payment_id": payment.id, "status": payment.status.value, "provider_txn_id": payment.provider_txn_id}


@router.post("/api/payments/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    if not razorpay.verify_webhook_signature(raw, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(400, "Invalid webhook signature")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Malformed webhook body") from None
    event = body.get("event", "") if isinstance(body, dict) else ""
    event_id = request.headers.get("x-razorpay-event-id") or hashlib.sha256(raw).hexdigest()
    if not _record_event(db, "razorpay", event_id, event, {"event": event}):
        return {"ok": True, "duplicate": True}
    entity = (body.get("payload", {}).get("payment") or {}).get("entity") or {}
    order_id = entity.get("order_id") or ((body.get("payload", {}).get("order") or {}).get("entity") or {}).get("id")
    payment = db.query(Payment).filter(Payment.provider_order_id == order_id).first() if order_id else None
    if payment is None:
        db.commit()
        return {"ok": True, "matched": False}
    if event in ("payment.captured", "order.paid"):
        if entity.get("amount") is not None and int(entity["amount"]) != razorpay.to_paise(payment.amount):
            log.error("Razorpay amount mismatch for payment %s", payment.id)
            payment.raw_provider_response = {**(payment.raw_provider_response or {}), "amount_mismatch": entity.get("amount")}
        else:
            _mark_paid(db, payment, entity.get("id") or payment.provider_txn_id or "", f"webhook:{event}")
    elif event == "payment.failed" and payment.status != PaymentStatus.SUCCESS:
        payment.status = PaymentStatus.FAILED  # a later success for the same order still wins
    db.commit()
    return {"ok": True, "status": payment.status.value}


# ----------------------------------------------------------------- WhatsApp

def _twiml(message: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message[:1500])}</Message></Response>',
                    media_type="application/xml")


CONFIRM_WORDS = {"yes", "y", "confirm", "ok", "haan", "ha", "houdu"}


@router.post("/api/whatsapp/inbound")
async def whatsapp_inbound(request: Request, db: Session = Depends(get_db)) -> Response:
    """Twilio inbound WhatsApp webhook. Text or voice note -> parsed order -> optimizer plans
    -> reply with the cheapest plan; replying YES approves it and notifies suppliers."""
    s = get_settings()
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    url = s.public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if not s.public_base_url or not whatsapp.verify_signature(url, params, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "Invalid Twilio signature")
    if not _record_event(db, "twilio", params.get("MessageSid", ""), "inbound_whatsapp", {"from": params.get("From", "")}):
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response/>', media_type="application/xml")

    phone = params.get("From", "").removeprefix("whatsapp:")
    user = db.query(User).filter(User.phone_e164 == phone, User.whatsapp_opt_in.is_(True), User.is_active.is_(True)).first()
    merchant = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first() if user and user.role == UserRole.MERCHANT else None
    if merchant is None:
        db.commit()
        return _twiml("This number is not linked to a Stockout Firewall merchant account. Add it under WhatsApp alerts in the app.")

    text = params.get("Body", "").strip()
    if int(params.get("NumMedia", "0") or 0) > 0 and params.get("MediaContentType0", "").startswith("audio"):
        if not s.sarvam_configured:
            db.commit()
            return _twiml("Voice notes need Sarvam speech-to-text, which is not configured. Please type your order.")
        try:
            audio, ctype = whatsapp.download_media(params["MediaUrl0"])
            text = sarvam.transcribe(audio, "voice-note." + ctype.split("/")[-1].split(";")[0], "unknown").transcript
        except (whatsapp.WhatsAppError, httpx.HTTPError):
            db.commit()
            return _twiml("Sorry, that voice note could not be transcribed. Please type your order.")

    if text.lower().strip(" .!") in CONFIRM_WORDS:
        since = datetime.now(UTC) - timedelta(hours=24)
        order = (db.query(Order).filter(Order.merchant_id == merchant.id, Order.status == OrderStatus.PLANNED,
                                        Order.raw_input_text.like("[WhatsApp]%"), Order.created_at >= since)
                 .order_by(Order.created_at.desc()).first())
        plan = min((p for p in order.plans if p.is_feasible and p.allocations), key=lambda p: p.total_cost, default=None) if order else None
        if plan is None:
            db.commit()
            return _twiml("There is no WhatsApp order waiting for confirmation. Send your order first, e.g. '100 kg akki'.")
        select_plan(db, order, plan.id)
        db.commit()
        return _twiml(f"Confirmed order #{order.id[:8]}: Rs.{plan.total_cost:,.0f}. Suppliers have been asked to confirm; "
                      "you will get updates here.")

    parsed = parse_order_text(text, db)
    if not parsed.items:
        db.commit()
        return _twiml("I could not find a product and quantity. Try: '100 kg akki' or '20 kg sugar, 10 litre oil'.")
    order = Order(merchant_id=merchant.id, raw_input_text=f"[WhatsApp] {text}"[:2000], parse_confidence=parsed.overall_confidence,
                  requires_confirmation=parsed.overall_confidence < LOW_CONFIDENCE_THRESHOLD or bool(parsed.unmatched_fragments),
                  price_tolerance_pct=merchant.default_budget_tolerance_pct, min_reliability=merchant.default_min_reliability)
    db.add(order)
    db.flush()
    for i in parsed.items:
        db.add(OrderItem(order_id=order.id, product_id=i.product_id, requested_qty_base_unit=i.quantity_base_unit))
    db.flush()
    db.refresh(order)
    summary = ", ".join(f"{i.quantity_base_unit:g} {i.base_unit} {i.product_name}" for i in parsed.items)
    if order.requires_confirmation:
        db.commit()
        return _twiml(f"I read: {summary}, but I am not sure about part of it. Please review order #{order.id[:8]} in the app.")
    plans = create_initial_plans(db, order)
    best = min((p for p in plans if p.is_feasible and p.allocations), key=lambda p: p.total_cost, default=None)
    db.commit()
    if best is None:
        return _twiml(f"I read: {summary}. No supplier can fully cover this within your default rules; open order #{order.id[:8]} in the app.")
    return _twiml(f"I read: {summary}. Best plan: Rs.{best.total_cost:,.0f} from {best.supplier_count} supplier(s), "
                  f"about {best.estimated_delivery_hours:g}h. Reply YES to confirm.")


# ------------------------------------------------------------------- routes

_route_cache: dict[tuple, dict] = {}


def _osrm(origin: tuple[float, float], dest: tuple[float, float]) -> dict | None:
    key = (round(origin[0], 4), round(origin[1], 4), round(dest[0], 4), round(dest[1], 4))
    if key in _route_cache:
        return _route_cache[key]
    s = get_settings()
    url = f"{s.osrm_base_url.rstrip('/')}/route/v1/driving/{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
    try:
        resp = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=8.0,
                         headers={"User-Agent": "StockoutFirewall/1.0"})
        body = resp.json()
        if resp.status_code != 200 or body.get("code") != "Ok" or not body.get("routes"):
            return None
    except (httpx.HTTPError, ValueError):
        return None
    r = body["routes"][0]
    out = {"source": "osrm", "distance_km": round(r["distance"] / 1000, 2), "duration_min": round(r["duration"] / 60, 1),
           "geometry": r["geometry"]}
    _route_cache[key] = out
    return out


@router.get("/api/orders/{order_id}/routes")
def order_routes(order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> dict:
    """Road routes for the active plan. Planning costs still use the labelled estimates;
    this shows the actual road route where the routing service answers."""
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(404, "Order not found")
    plan = get_selected_plan(order)
    lines = []
    inactive = (AllocationStatus.REJECTED, AllocationStatus.EXPIRED, AllocationStatus.SUPERSEDED)
    for a in (plan.allocations if plan else []):
        if a.status in inactive:
            continue
        sup = db.get(SupplierProfile, a.supplier_id)
        route = _osrm((sup.latitude, sup.longitude), (merchant.latitude, merchant.longitude)) if get_settings().routing_enabled else None
        lines.append({"allocation_id": a.id, "supplier_name": sup.business_name, "lat": sup.latitude, "lon": sup.longitude,
                      "product_name": a.product.name, "qty": a.confirmed_qty_base_unit if a.confirmed_qty_base_unit is not None else a.allocated_qty_base_unit,
                      "status": a.status.value, "planner_estimate_km": a.route_distance_km,
                      "route": route or {"source": "estimated", "distance_km": a.route_distance_km,
                                         "duration_min": a.route_duration_minutes, "geometry": None}})
    return {"merchant": {"name": merchant.business_name, "lat": merchant.latitude, "lon": merchant.longitude},
            "lines": lines, "attribution": "Routes: OSRM / OpenStreetMap contributors"}
