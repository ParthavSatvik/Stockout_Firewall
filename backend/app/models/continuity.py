"""Supplier Continuity Network: Supply Relay Protocol and the commitment ledger.

Statuses are plain strings (not DB enums) so new protocol states never need an
ALTER TYPE migration on PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class SupplyRelay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A supplier-initiated request for partner wholesalers to cover its shortfall.

    open -> (partners respond) -> approved | declined | fallback | expired | cancelled
    Nothing a partner says is binding until the merchant approves; partner stock is
    reserved atomically at that moment, never before.
    """

    __tablename__ = "supply_relays"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    order_item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    origin_supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), index=True)
    origin_allocation_id: Mapped[str] = mapped_column(ForeignKey("allocations.id"))
    source_plan_id: Mapped[str] = mapped_column(ForeignKey("allocation_plans.id"))
    outstanding_qty_base_unit: Mapped[float] = mapped_column(Float)
    origin_committed_qty_base_unit: Mapped[float] = mapped_column(Float, default=0.0)
    price_ceiling_per_base_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    needed_by: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    resolution_note: Mapped[str] = mapped_column(String(300), default="")
    resolved_plan_id: Mapped[str | None] = mapped_column(ForeignKey("allocation_plans.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    invites: Mapped[list[SupplyRelayInvite]] = relationship(
        back_populates="relay", cascade="all, delete-orphan", order_by="SupplyRelayInvite.created_at"
    )
    origin_supplier = relationship("SupplierProfile", foreign_keys=[origin_supplier_id])
    product = relationship("Product")


class SupplyRelayInvite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One partner's view of a relay: eligibility evidence at invite time plus its answer.

    invited -> accepted | modified | declined; after merchant approval -> reserved |
    reservation_failed | not_selected.
    """

    __tablename__ = "supply_relay_invites"

    relay_id: Mapped[str] = mapped_column(ForeignKey("supply_relays.id"), index=True)
    partner_supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), index=True)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("supplier_inventory.id"))
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="invited", index=True)
    offered_qty_base_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    offered_price_per_base_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    offered_ready_by: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    relay: Mapped[SupplyRelay] = relationship(back_populates="invites")
    partner_supplier = relationship("SupplierProfile", foreign_keys=[partner_supplier_id])


class CommitmentLedgerEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only audit of every supplier-side commitment change: who, what, from
    which state to which, how much and why. Never updated or deleted by the app."""

    __tablename__ = "commitment_ledger"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("supplier_profiles.id"), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    allocation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    inventory_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    relay_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    qty_base_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    visible_to_merchant: Mapped[bool] = mapped_column(Boolean, default=True)
