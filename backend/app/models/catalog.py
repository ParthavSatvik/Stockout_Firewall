from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin, utcnow
from app.models.core import MerchantProfile, SupplierProfile


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical product -- the normalization target for free-text order parsing."""

    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    base_unit: Mapped[str] = mapped_column(String(20))  # kg, litre, piece

    aliases: Mapped[list[ProductAlias]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductAlias(Base, UUIDPrimaryKeyMixin):
    """Lexicon entries used by the deterministic SKU-normalization parser.

    Covers Kannada/Hindi/English code-mixed spellings (e.g. 'akki', 'chawal', 'rice').
    """

    __tablename__ = "product_aliases"

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    alias_text: Mapped[str] = mapped_column(String(150), index=True)
    language: Mapped[str] = mapped_column(String(10), default="en")

    product: Mapped[Product] = relationship(back_populates="aliases")


class SupplierInventory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Current offer from a supplier for a product pack: price, stock, MOQ."""

    __tablename__ = "supplier_inventory"

    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    brand: Mapped[str] = mapped_column(String(100), default="generic")
    pack_size: Mapped[float] = mapped_column(Float)  # e.g. 25.0
    pack_unit: Mapped[str] = mapped_column(String(20))  # kg, litre, piece
    price_per_base_unit: Mapped[float] = mapped_column(Float)  # INR per kg/litre/piece
    stock_qty_base_unit: Mapped[float] = mapped_column(Float)  # total available, in base unit
    moq_base_unit: Mapped[float] = mapped_column(Float, default=0.0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    freshness_source: Mapped[str] = mapped_column(String(30), default="manual")  # manual|synced|stale

    supplier: Mapped[SupplierProfile] = relationship()
    product: Mapped[Product] = relationship()


class PriceObservation(Base, UUIDPrimaryKeyMixin):
    """Historical price point, used for the Local Wholesale Price Index and margin-leak detection."""

    __tablename__ = "price_observations"

    supplier_id: Mapped[str] = mapped_column(ForeignKey("supplier_profiles.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    price_per_base_unit: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SurplusListing(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Dead-Stock Rescue Exchange: supplier- or merchant-listed excess inventory."""

    __tablename__ = "surplus_listings"

    lister_supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("supplier_profiles.id"), nullable=True
    )
    lister_merchant_id: Mapped[str | None] = mapped_column(
        ForeignKey("merchant_profiles.id"), nullable=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    qty_base_unit: Mapped[float] = mapped_column(Float)
    asking_price_per_base_unit: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|matched|closed

    product: Mapped[Product] = relationship()


class MerchantProductPrice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Merchant-entered selling price for a product, used by the Margin Leak Detector.

    This is an explicit merchant input, not inferred from any transaction -- there is no
    POS integration in this prototype.
    """

    __tablename__ = "merchant_product_prices"

    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchant_profiles.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    selling_price_per_base_unit: Mapped[float] = mapped_column(Float)

    merchant: Mapped[MerchantProfile] = relationship()
    product: Mapped[Product] = relationship()


class SurplusOffer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A counter-offer against a SurplusListing in the Dead-Stock Rescue Exchange."""

    __tablename__ = "surplus_offers"

    listing_id: Mapped[str] = mapped_column(ForeignKey("surplus_listings.id"), index=True)
    offerer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    qty_requested_base_unit: Mapped[float] = mapped_column(Float)
    offered_price_per_base_unit: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted|declined

    listing: Mapped[SurplusListing] = relationship()
