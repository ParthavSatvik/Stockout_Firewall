from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.ops import PaymentProvider, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    order_id: str
    # Simulated checkout only. Test instruments, never real card or bank details.
    method: Literal["upi", "card", "netbanking"] = "upi"
    instrument: str = Field(default="success@upi", max_length=60)


class PaymentRead(BaseModel):
    id: str
    order_id: str
    provider: PaymentProvider
    amount: float
    currency: str
    status: PaymentStatus
    provider_order_id: str
    provider_txn_id: str | None
    is_simulated: bool
    created_at: datetime | None = None
    raw_provider_response: dict = {}

    model_config = {"from_attributes": True}
