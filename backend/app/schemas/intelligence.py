from pydantic import BaseModel, Field


class SurvivalModeItem(BaseModel):
    product_id: str
    product_name: str
    requested_qty_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    priority: int = Field(ge=1, le=5)


class SurvivalModeRequest(BaseModel):
    items: list[SurvivalModeItem] = Field(min_length=1, max_length=50)
    budget_cap: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    price_tolerance_pct: float = Field(default=15, ge=0, le=1000, allow_inf_nan=False)
    min_reliability: float = Field(default=.4, ge=0, le=1, allow_inf_nan=False)
    max_suppliers: int = Field(default=4, ge=1, le=20)


class CashCycleInputRequest(BaseModel):
    available_cash_on_hand: float = Field(ge=0, le=100000000, allow_inf_nan=False)


class SellingPriceUpsertRequest(BaseModel):
    product_id: str
    selling_price_per_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)


class SurplusOfferCreateRequest(BaseModel):
    qty_requested_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    offered_price_per_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
