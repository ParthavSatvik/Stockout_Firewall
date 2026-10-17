from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
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
    RAZORPAY = "razorpay"


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


class ProviderEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Every verified inbound provider event (Razorpay webhook, Twilio message), keyed by
    the provider's own id so retries are processed exactly once."""

    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_provider_event"),)

    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(60), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class OutboundMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """WhatsApp (or other channel) message log. status: queued|sent|failed|skipped."""

    __tablename__ = "outbound_messages"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    kind: Mapped[str] = mapped_column(String(40))
    to_address: Mapped[str] = mapped_column(String(40), default="")
    body: Mapped[str] = mapped_column(String(1600))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    provider_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str] = mapped_column(String(300), default="")


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
