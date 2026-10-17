from datetime import datetime

from pydantic import BaseModel, Field


class ProductRead(BaseModel):
    id: str
    name: str
    category: str
    base_unit: str

    model_config = {"from_attributes": True}


class SupplierInventoryRead(BaseModel):
    id: str
    supplier_id: str
    supplier_name: str
    product_id: str
    product_name: str
    brand: str
    pack_size: float
    pack_unit: str
    price_per_base_unit: float
    stock_qty_base_unit: float
    moq_base_unit: float
    is_available: bool
    freshness_source: str
    reliability_score: float
    reliability_confidence: str
    reliability_sample_size: int
    safety_stock_base_unit: float = 0.0
    committed_qty_base_unit: float = 0.0
    free_to_promise_base_unit: float = 0.0
    stock_confirmed_at: datetime | None = None


class InventoryUpsertRequest(BaseModel):
    product_id: str
    brand: str = Field(default="generic", min_length=1, max_length=100)
    pack_size: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    pack_unit: str
    price_per_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    # Physical stock on hand. Live commitments are subtracted server-side so they are
    # never promised twice.
    stock_qty_base_unit: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    moq_base_unit: float = Field(default=0, ge=0, le=1000000, allow_inf_nan=False)
    is_available: bool = True
    safety_stock_base_unit: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)


class StockCountRequest(BaseModel):
    on_hand_base_unit: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    safety_stock_base_unit: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    reason: str = Field(default="", max_length=300)


class SurplusListingCreate(BaseModel):
    product_id: str
    qty_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    asking_price_per_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)


class SurplusListingRead(BaseModel):
    id: str
    product_id: str
    product_name: str
    qty_base_unit: float
    asking_price_per_base_unit: float
    status: str
    lister_type: str  # "merchant" | "supplier"
    lister_name: str
    is_mine: bool = False
    pending_offer_count: int = 0
    my_offer: "SurplusOfferRead | None" = None

    model_config = {"from_attributes": True}


class SurplusOfferCreate(BaseModel):
    qty_requested_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    offered_price_per_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)


class SurplusOfferRead(BaseModel):
    id: str
    listing_id: str
    offerer_user_id: str
    qty_requested_base_unit: float
    offered_price_per_base_unit: float
    status: str
    offerer_name: str = ""

    model_config = {"from_attributes": True}


SurplusListingRead.model_rebuild()
