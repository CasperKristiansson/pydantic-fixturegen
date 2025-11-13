"""Payment intents, captures, and refunds."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from .shared import MarketplaceBaseModel, Money, Timestamped


class PaymentProvider(str, Enum):
    stripe = "stripe"
    klarna = "klarna"
    swish = "swish"


class PaymentIntent(Timestamped):
    intent_id: UUID
    customer_id: UUID
    provider: PaymentProvider
    amount: Money
    statement_descriptor: str
    expires_at: datetime


class CaptureStatus(str, Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class PaymentCapture(MarketplaceBaseModel):
    capture_id: UUID
    intent_id: UUID
    status: CaptureStatus
    requested_at: datetime
    captured_at: datetime | None = None
    amount: Money
    retries: Annotated[int, Field(ge=0, le=5)] = 0
    failure_reason: str | None = None


class Refund(MarketplaceBaseModel):
    refund_id: UUID
    capture_id: UUID
    amount: Money
    issued_at: datetime
    reason: str
