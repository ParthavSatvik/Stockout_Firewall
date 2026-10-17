from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.orders import AllocationStatus, ObjectiveProfile, OrderStatus


class OrderItemCreate(BaseModel):
    model_config = {"allow_inf_nan": False}
    product_id: str
    requested_qty_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    substitution_allowed: bool = True
    notes: str = Field(default="", max_length=300)


class OrderCreate(BaseModel):
    model_config = {"allow_inf_nan": False}
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)
    objective_profile: ObjectiveProfile = ObjectiveProfile.CHEAPEST
    budget_cap: float | None = Field(default=None, ge=0, le=100000000)
    price_tolerance_pct: float = Field(default=10.0, ge=0, le=1000)
    min_reliability: float = Field(default=0.6, ge=0, le=1)
    allow_substitution: bool = True
    max_suppliers: int = Field(default=4, ge=1, le=20)
    preferred_supplier_ids: list[str] = Field(default=[], max_length=20)
    raw_input_text: str = Field(default="", max_length=5000)
    raw_input_language: str = Field(default="en", max_length=10)


class OrderItemRead(BaseModel):
    id: str
    product_id: str
    product_name: str
    requested_qty_base_unit: float
    substitution_allowed: bool
    notes: str

    model_config = {"from_attributes": True}


class AllocationRead(BaseModel):
    id: str
    plan_id: str
    order_item_id: str
    supplier_id: str
    supplier_name: str
    product_id: str
    product_name: str
    allocated_qty_base_unit: float
    unit_price: float
    pack_count: int
    status: AllocationStatus
    confirmed_qty_base_unit: float | None
    confirmed_ready_by: datetime | None
    confirmation_expires_at: datetime | None
    route_distance_km: float | None
    route_duration_minutes: float | None
    route_source: str
    route_cost: float
    fulfillment_stage: str | None = None

    model_config = {"from_attributes": True}


class AllocationPlanRead(BaseModel):
    id: str
    order_id: str
    objective_profile: ObjectiveProfile
    is_selected: bool
    is_feasible: bool
    replan_reason: str
    total_product_cost: float
    total_delivery_cost: float
    total_risk_penalty: float
    total_cost: float
    estimated_delivery_hours: float
    supplier_count: int
    explanation: dict
    infeasible_reasons: list
    created_at: datetime
    allocations: list[AllocationRead]

    model_config = {"from_attributes": True}


class OrderRead(BaseModel):
    id: str
    merchant_id: str
    status: OrderStatus
    objective_profile: ObjectiveProfile
    budget_cap: float | None
    price_tolerance_pct: float
    min_reliability: float
    allow_substitution: bool
    max_suppliers: int
    requires_confirmation: bool
    parse_confidence: float
    raw_input_text: str
    created_at: datetime
    items: list[OrderItemRead]
    plans: list[AllocationPlanRead]

    model_config = {"from_attributes": True}


class PlanComparisonResponse(BaseModel):
    order_id: str
    plans: list[AllocationPlanRead]


class SelectPlanRequest(BaseModel):
    plan_id: str


class AllocationConfirmRequest(BaseModel):
    confirmed_qty_base_unit: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    ready_by: datetime
    # Dipping into safety stock is allowed only as an explicit, recorded decision.
    override_safety_stock: bool = False
    override_reason: str = Field(default="", max_length=300)


RejectReasonCode = Literal["out_of_stock", "insufficient_capacity", "price_changed", "delivery_window", "quality_issue", "other"]


class AllocationRejectRequest(BaseModel):
    reason: str = Field(default="", max_length=300)
    reason_code: RejectReasonCode = "other"


class StageUpdateRequest(BaseModel):
    stage: Literal["picking", "ready"]
    note: str = Field(default="", max_length=300)


class RelayOpenRequest(BaseModel):
    """Commit what you can (0 allowed) and ask partner wholesalers for the rest."""
    commit_qty_base_unit: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    ready_by: datetime | None = None
    reason: str = Field(min_length=3, max_length=300)
    response_window_minutes: int = Field(default=120, ge=15, le=720)


class RelayRespondRequest(BaseModel):
    action: Literal["accept", "modify", "decline"]
    qty_base_unit: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    price_per_base_unit: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    ready_by: datetime | None = None
    note: str = Field(default="", max_length=300)


class RelayDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=300)


class AllocationShortfallRequest(BaseModel):
    actual_deliverable_qty_base_unit: float = Field(ge=0, le=1000000, allow_inf_nan=False)
    reason: str = ""


class ReceiptCreate(BaseModel):
    allocation_id: str
    product_id: str
    received_qty_base_unit: float = Field(ge=0, le=1000000, allow_inf_nan=False)


class InvoiceItemCreate(BaseModel):
    product_id: str
    qty_base_unit: float = Field(gt=0, allow_inf_nan=False)
    unit_price: float = Field(ge=0, allow_inf_nan=False)


class InvoiceCreate(BaseModel):
    order_id: str
    invoice_number: str = Field(default="", max_length=80)
    items: list[InvoiceItemCreate]


class ReconciliationLine(BaseModel):
    product_id: str
    product_name: str
    ordered_qty: float
    invoiced_qty: float
    received_qty: float
    ordered_vs_invoiced_diff: float
    invoiced_vs_received_diff: float
    invoiced_unit_price: float | None
    allocated_unit_price: float | None
    price_diff: float | None
    flags: list[str]


class ReconciliationResponse(BaseModel):
    order_id: str
    lines: list[ReconciliationLine]
    has_discrepancies: bool
