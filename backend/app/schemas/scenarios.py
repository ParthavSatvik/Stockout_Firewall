from pydantic import BaseModel


class ScenarioDisruptionRequest(BaseModel):
    """Digital Twin control: apply a disruption to an existing confirmed order and
    observe the automatic failover/replan. Reuses the same failover engine the real
    supplier-reported-shortfall path uses, so the simulation is not a fake UI effect."""

    order_id: str
    allocation_id: str
    disruption_type: str  # "supplier_outage" | "price_increase" | "partial_stock" | "delivery_delay"
    magnitude_pct: float = 0.0  # e.g. price increase % or stock reduction %
    description: str = ""


class ScenarioResultResponse(BaseModel):
    order_id: str
    disruption_type: str
    before_plan_id: str
    after_plan_id: str
    before_total_cost: float
    after_total_cost: float
    before_delivery_hours: float
    after_delivery_hours: float
    narrative: str
