from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ObjectiveProfile(str, enum.Enum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    MOST_RELIABLE = "most_reliable"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REPLANNING = "replanning"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    FULFILLED = "fulfilled"
    INFEASIBLE = "infeasible"
    CANCELLED = "cancelled"


class AllocationStatus(str, enum.Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SHORT_SUPPLY = "short_supply"
    FULFILLED = "fulfilled"
    SUPERSEDED = "superseded"  # replaced by a later replan


class SupplierEventType(str, enum.Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SHORT_SUPPLY = "short_supply"
    EXPIRED = "expired"
    DISRUPTED = "disrupted"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"

    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchant_profiles.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.DRAFT, index=True)
    objective_profile: Mapped[ObjectiveProfile] = mapped_column(
        Enum(ObjectiveProfile), default=ObjectiveProfile.CHEAPEST
    )
    raw_input_text: Mapped[str] = mapped_column(Text, default="")
    raw_input_language: Mapped[str] = mapped_column(String(10), default="en")
    parse_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)

    # Merchant policy snapshot for this order (immutable once planned)
    budget_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=10.0)
    min_reliability: Mapped[float] = mapped_column(Float, default=0.6)
    allow_substitution: Mapped[bool] = mapped_column(Boolean, default=True)
    max_suppliers: Mapped[int] = mapped_column(Integer, default=4)
    preferred_supplier_ids: Mapped[list] = mapped_column(JSON, default=list)

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    plans: Mapped[list[AllocationPlan]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    requested_qty_base_unit: Mapped[float] = mapped_column(Float)
    substitution_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(300), default="")

    order: Mapped[Order] = relationship(back_populates="items")
    product = relationship("Product")

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else self.product_id


class AllocationPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One optimizer run's output for an order under a given objective profile.

    A replan after a disruption creates a new plan row rather than mutating the old one,
    so the full history of recovery decisions stays auditable.
    """

    __tablename__ = "allocation_plans"

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    objective_profile: Mapped[ObjectiveProfile] = mapped_column(Enum(ObjectiveProfile))
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    replan_reason: Mapped[str] = mapped_column(String(200), default="initial")
    total_product_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_delivery_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_risk_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_delivery_hours: Mapped[float] = mapped_column(Float, default=0.0)
    supplier_count: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    infeasible_reasons: Mapped[list] = mapped_column(JSON, default=list)

    order: Mapped[Order] = relationship(back_populates="plans")
    allocations: Mapped[list[Allocation]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class Allocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single supplier/product line within an allocation plan."""

    __tablename__ = "allocations"

    inventory_id: Mapped[str | None] = mapped_column(ForeignKey("supplier_inventory.id"), nullable=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("allocation_plans.id"), index=True)
    order_item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    allocated_qty_base_unit: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    pack_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus), default=AllocationStatus.PROPOSED, index=True
    )
    confirmed_qty_base_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_ready_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    route_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_source: Mapped[str] = mapped_column(String(20), default="estimated")  # estimated|google_routes
    route_cost: Mapped[float] = mapped_column(Float, default=0.0)

    plan: Mapped[AllocationPlan] = relationship(back_populates="allocations")
    order_item: Mapped[OrderItem] = relationship()
    supplier = relationship("SupplierProfile")
    product = relationship("Product")
    events: Mapped[list[SupplierEvent]] = relationship(
        back_populates="allocation", cascade="all, delete-orphan"
    )

    @property
    def supplier_name(self) -> str:
        return self.supplier.business_name if self.supplier else self.supplier_id

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else self.product_id


class SupplierEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only log of everything a supplier (or the system) reports about an allocation.

    This is what drives failover: a short_supply/rejected/expired/disrupted event here
    triggers the replan service.
    """

    __tablename__ = "supplier_events"

    allocation_id: Mapped[str] = mapped_column(ForeignKey("allocations.id"), index=True)
    event_type: Mapped[SupplierEventType] = mapped_column(Enum(SupplierEventType), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    triggered_replan: Mapped[bool] = mapped_column(Boolean, default=False)

    allocation: Mapped[Allocation] = relationship(back_populates="events")
