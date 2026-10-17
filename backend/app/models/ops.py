from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin, utcnow


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentProvider(str, enum.Enum):
    SIMULATED = "simulated"
    PAYTM = "paytm"


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    provider_order_id: Mapped[str] = mapped_column(String(100), default="")
    provider_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    raw_provider_response: Mapped[dict] = mapped_column(JSON, default=dict)
    is_simulated: Mapped[bool] = mapped_column(default=True)


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "invoices"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"))
    invoice_number: Mapped[str] = mapped_column(String(80), default="")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)

    items: Mapped[list[InvoiceItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    qty_base_unit: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class ReceiptRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What the merchant actually received, for the Order Truth Engine reconciliation
    (ordered vs invoiced vs received)."""

    __tablename__ = "receipt_records"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    allocation_id: Mapped[str] = mapped_column(ForeignKey("allocations.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    received_qty_base_unit: Mapped[float] = mapped_column(Float)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(default=False)
    related_order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class SupplierReliabilityStat(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recomputed from supplier_events history. `confidence` reflects sample size,
    not a fabricated accuracy figure -- small samples are explicitly marked low confidence.
    """

    __tablename__ = "supplier_reliability_stats"

    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), unique=True, index=True)
    total_commitments: Mapped[int] = mapped_column(Integer, default=0)
    fulfilled_count: Mapped[int] = mapped_column(Integer, default=0)
    short_supply_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, default=0)
    on_time_count: Mapped[int] = mapped_column(Integer, default=0)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high
    sample_size: Mapped[int] = mapped_column(Integer, default=0)


class ScenarioSimulation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Supply Chain Digital Twin: a named, replayable disruption scenario."""

    __tablename__ = "scenario_simulations"

    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_result: Mapped[dict] = mapped_column(JSON, default=dict)
