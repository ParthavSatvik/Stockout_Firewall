"""Order notifications: an in-app Notification always, plus a WhatsApp message when the
user has opted in with a number and Twilio is configured.

Messages are queued inside the business transaction (so they exist only if the change
committed) and sent after the HTTP response by `dispatch_queued`. A send is claimed with a
compare-and-set so concurrent dispatchers never send the same message twice. Every
outcome -- sent, failed, skipped (and why) -- is recorded; nothing is reported as sent
unless Twilio returned a message SID.
"""
from __future__ import annotations

import logging

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import User
from app.models.ops import Notification, OutboundMessage
from app.providers import whatsapp

log = logging.getLogger(__name__)


def notify(db: Session, user_id: str, kind: str, title: str, body: str, order_id: str | None = None) -> None:
    db.add(Notification(user_id=user_id, type=kind, title=title[:200], message=body[:500], related_order_id=order_id))
    user = db.get(User, user_id)
    if user is None:
        return
    if not (user.whatsapp_opt_in and user.phone_e164):
        status, error = "skipped", "user has not opted in to WhatsApp"
    elif not get_settings().twilio_configured:
        status, error = "skipped", "Twilio WhatsApp not configured"
    else:
        status, error = "queued", ""
    db.add(OutboundMessage(user_id=user_id, order_id=order_id, kind=kind, to_address=user.phone_e164 or "",
                           body=f"Stockout Firewall: {body}"[:1600], status=status, error=error))


def dispatch_queued(limit: int = 20) -> int:
    from app.database import SessionLocal

    sent = 0
    with SessionLocal() as db:
        ids = [m.id for m in db.query(OutboundMessage.id).filter(OutboundMessage.status == "queued").limit(limit)]
        for mid in ids:
            claimed = db.execute(update(OutboundMessage).where(OutboundMessage.id == mid, OutboundMessage.status == "queued")
                                 .values(status="sending"))
            db.commit()
            if claimed.rowcount != 1:
                continue
            msg = db.get(OutboundMessage, mid)
            try:
                msg.provider_sid = whatsapp.send(msg.to_address, msg.body)
                msg.status = "sent"
                sent += 1
            except Exception as exc:  # network errors included; record, never raise into the request
                msg.status, msg.error = "failed", str(exc)[:300]
                log.warning("WhatsApp send failed for %s: %s", mid, msg.error)
            db.commit()
    return sent


def merchant_user_id(db: Session, order) -> str | None:
    from app.models.core import MerchantProfile

    merchant = db.get(MerchantProfile, order.merchant_id)
    return merchant.user_id if merchant else None


def supplier_user_id(db: Session, supplier_id: str) -> str | None:
    from app.models.core import SupplierProfile

    supplier = db.get(SupplierProfile, supplier_id)
    return supplier.user_id if supplier else None


def announce_new_requests(db: Session, plan, already_announced: set | None = None) -> None:
    """Tell each supplier about lines newly proposed to it on `plan`."""
    from app.models.orders import AllocationStatus

    for a in plan.allocations:
        if a.status != AllocationStatus.PROPOSED or (a.order_item_id, a.supplier_id, a.inventory_id) in (already_announced or set()):
            continue
        uid = supplier_user_id(db, a.supplier_id)
        if uid:
            notify(db, uid, "new_request", "New order request",
                   f"New request: {a.allocated_qty_base_unit:g} {a.product.base_unit} {a.product.name} at Rs.{a.unit_price:g}. "
                   "Review it in PromiseGuard before it expires.", a.plan.order_id)


def announce_replan(db: Session, order, plan, reason: str) -> None:
    uid = merchant_user_id(db, order)
    if uid is None:
        return
    shortfall = sum((plan.explanation or {}).get("shortfall_by_item", {}).values())
    tail = f" {shortfall:g} still uncovered -- review the order." if shortfall > 1e-6 else ""
    notify(db, uid, "recovery", "Supplier issue -- order re-planned",
           f"Order #{order.id[:8]}: supplier {reason.replace('_', ' ')}. New plan total Rs.{plan.total_cost:,.0f}, "
           f"est. delivery {plan.estimated_delivery_hours:g}h.{tail}", order.id)
    if reason == "supply_relay":
        return  # partners were told by the relay itself; their stock is reserved right after
    from app.models.orders import AllocationPlan, AllocationStatus

    previous = db.get(AllocationPlan, (plan.explanation or {}).get("previous_plan_id") or "")
    seen = {(a.order_item_id, a.supplier_id, a.inventory_id) for a in (previous.allocations if previous else [])
            if a.status == AllocationStatus.PROPOSED}
    announce_new_requests(db, plan, seen)
