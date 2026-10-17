from pydantic import BaseModel

from app.models.ops import PaymentProvider, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    order_id: str


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

    model_config = {"from_attributes": True}
