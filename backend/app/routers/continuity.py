"""Supplier Continuity Network endpoints: Promise Ledger, Commitment Copilot, dispatch
board, Trust Passport, Supply Relay Protocol and the shared commitment audit trail."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile, get_supplier_profile
from app.models.continuity import CommitmentLedgerEntry, SupplyRelay, SupplyRelayInvite
from app.models.core import MerchantProfile, SupplierProfile, User
from app.models.orders import Order
from app.schemas.orders import RelayDecisionRequest, RelayRespondRequest
from app.security import get_current_user
from app.services import copilot as copilot_service
from app.services import relay as relay_service

router = APIRouter(tags=["supplier-continuity"])


def _entry(e: CommitmentLedgerEntry, names: dict[str, str]) -> dict:
    return {"id": e.id, "at": e.created_at, "action": e.action, "actor_role": e.actor_role,
            "supplier_name": names.get(e.supplier_id or "", None), "from_state": e.from_state, "to_state": e.to_state,
            "qty": e.qty_base_unit, "reason": e.reason, "payload": e.payload, "allocation_id": e.allocation_id,
            "relay_id": e.relay_id}


def _supplier_names(db: Session) -> dict[str, str]:
    return {s.id: s.business_name for s in db.query(SupplierProfile).all()}


# ------------------------------------------------------------------ supplier views

@router.get("/api/suppliers/me/promise-ledger")
def promise_ledger(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> dict:
    return copilot_service.promise_ledger(db, supplier)


@router.get("/api/suppliers/me/copilot")
def commitment_copilot(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> dict:
    return copilot_service.copilot(db, supplier)


@router.get("/api/suppliers/me/dispatch-board")
def dispatch_board(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> dict:
    return copilot_service.dispatch_board(db, supplier)


@router.get("/api/suppliers/me/passport")
def my_passport(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> dict:
    return copilot_service.passport(db, supplier)


@router.get("/api/suppliers/me/ledger-events")
def my_ledger_events(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> list[dict]:
    rows = (db.query(CommitmentLedgerEntry).filter(CommitmentLedgerEntry.supplier_id == supplier.id)
            .order_by(CommitmentLedgerEntry.created_at.desc()).limit(200).all())
    names = _supplier_names(db)
    return [_entry(e, names) for e in rows]


@router.get("/api/network/suppliers/{supplier_id}/passport")
def network_passport(supplier_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Aggregate, order-free passport any signed-in participant may inspect."""
    supplier = db.get(SupplierProfile, supplier_id)
    if supplier is None or not supplier.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return copilot_service.passport(db, supplier)


# --------------------------------------------------------------------- relays

@router.get("/api/relays/mine")
def my_relays(db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> dict:
    relay_service.expire_due_relays(db)
    db.commit()
    outgoing = (db.query(SupplyRelay).filter(SupplyRelay.origin_supplier_id == supplier.id)
                .order_by(SupplyRelay.created_at.desc()).limit(50).all())
    incoming = (db.query(SupplyRelay).join(SupplyRelayInvite, SupplyRelayInvite.relay_id == SupplyRelay.id)
                .filter(SupplyRelayInvite.partner_supplier_id == supplier.id)
                .order_by(SupplyRelay.created_at.desc()).limit(50).all())
    return {"outgoing": [relay_service.relay_view(db, r, "origin") for r in outgoing],
            "incoming": [relay_service.relay_view(db, r, "partner", supplier.id) for r in incoming]}


@router.get("/api/relays/{relay_id}/candidates")
def relay_candidates(relay_id: str, db: Session = Depends(get_db), supplier: SupplierProfile = Depends(get_supplier_profile)) -> list[dict]:
    """Origin supplier only: who was eligible and exactly why others were not."""
    relay = db.get(SupplyRelay, relay_id)
    if relay is None or relay.origin_supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relay not found")
    order = db.get(Order, relay.order_id)
    return relay_service.candidates(db, order, relay.product_id, supplier.id, relay.outstanding_qty_base_unit,
                                    relay.price_ceiling_per_base_unit, relay.required_brand)


@router.post("/api/relays/invites/{invite_id}/respond")
def respond_to_relay(
    invite_id: str, payload: RelayRespondRequest, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile), user: User = Depends(get_current_user),
) -> dict:
    invite = db.get(SupplyRelayInvite, invite_id)
    if invite is None or invite.partner_supplier_id != supplier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    if relay_service.expire_if_due(db, invite.relay):
        db.commit()
        raise HTTPException(409, "The response window has closed; the merchant's open-market recovery took over")
    relay_service.respond(db, user, supplier, invite, payload.action, payload.qty_base_unit,
                          payload.price_per_base_unit, payload.ready_by, payload.note)
    db.commit()
    db.refresh(invite)
    return relay_service.relay_view(db, invite.relay, "partner", supplier.id)


# ------------------------------------------------------------------ merchant side

def _merchant_order(db: Session, order_id: str, merchant: MerchantProfile) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _merchant_relay(db: Session, order: Order, relay_id: str) -> SupplyRelay:
    relay = db.get(SupplyRelay, relay_id)
    if relay is None or relay.order_id != order.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relay not found")
    return relay


@router.get("/api/orders/{order_id}/relays")
def order_relays(order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    order = _merchant_order(db, order_id, merchant)
    relay_service.expire_due_relays(db, order.id)
    db.commit()
    relays = db.query(SupplyRelay).filter(SupplyRelay.order_id == order.id).order_by(SupplyRelay.created_at.desc()).all()
    out = []
    for r in relays:
        view = relay_service.relay_view(db, r, "merchant")
        view["preview"] = relay_service.preview(db, r) if r.status == "open" else None
        out.append(view)
    return out


@router.post("/api/orders/{order_id}/relays/{relay_id}/approve")
def approve_relay(
    order_id: str, relay_id: str, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile), user: User = Depends(get_current_user),
) -> dict:
    order = _merchant_order(db, order_id, merchant)
    relay = _merchant_relay(db, order, relay_id)
    if relay_service.expire_if_due(db, relay):
        db.commit()
        raise HTTPException(409, "The relay window closed before approval; open-market recovery ran instead")
    plan = relay_service.approve(db, user, relay)
    db.commit()
    return {"relay": relay_service.relay_view(db, relay, "merchant"), "plan_id": plan.id, "order_status": order.status.value}


@router.post("/api/orders/{order_id}/relays/{relay_id}/decline")
def decline_relay(
    order_id: str, relay_id: str, payload: RelayDecisionRequest, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile), user: User = Depends(get_current_user),
) -> dict:
    order = _merchant_order(db, order_id, merchant)
    relay = _merchant_relay(db, order, relay_id)
    plan = relay_service.decline(db, user, relay, payload.note or "Merchant chose open-market recovery")
    db.commit()
    return {"relay": relay_service.relay_view(db, relay, "merchant"), "plan_id": plan.id if plan else None, "order_status": order.status.value}


@router.get("/api/orders/{order_id}/commitment-ledger")
def order_commitment_ledger(order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)) -> list[dict]:
    """The same audit trail the suppliers see, filtered to this order."""
    order = _merchant_order(db, order_id, merchant)
    rows = (db.query(CommitmentLedgerEntry)
            .filter(CommitmentLedgerEntry.order_id == order.id, or_(CommitmentLedgerEntry.visible_to_merchant.is_(True)))
            .order_by(CommitmentLedgerEntry.created_at).all())
    names = _supplier_names(db)
    return [_entry(e, names) for e in rows]
