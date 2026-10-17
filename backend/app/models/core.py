from __future__ import annotations

import enum

from sqlalchemy import Enum, Float, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    MERCHANT = "merchant"
    SUPPLIER = "supplier"
    ADMIN = "admin"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supabase_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    # WhatsApp contact, E.164 (+919876543210). Messages are sent only with explicit opt-in.
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    whatsapp_opt_in: Mapped[bool] = mapped_column(default=False, server_default=false())

    merchant_profile: Mapped[MerchantProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    supplier_profile: Mapped[SupplierProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class MerchantProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "merchant_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    business_name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(300), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    default_budget_tolerance_pct: Mapped[float] = mapped_column(Float, default=10.0)
    default_min_reliability: Mapped[float] = mapped_column(Float, default=0.6)
    # Merchant-entered input for the Cash-Cycle Planner. Nullable because it is an
    # input the merchant must supply -- never inferred or fabricated as a bank balance.
    available_cash_on_hand: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[User] = relationship(back_populates="merchant_profile")


class SupplierProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "supplier_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    business_name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(300), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    operating_hours: Mapped[str] = mapped_column(String(100), default="09:00-20:00")
    delivery_capacity_kg_per_day: Mapped[float] = mapped_column(Float, default=1000.0)
    is_active: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(back_populates="supplier_profile")
