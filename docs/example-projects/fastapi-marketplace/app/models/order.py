"""Order aggregates referencing catalog, customer, payments, and notifications."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from .catalog import CatalogVariant
from .customer import CustomerProfile, DeliverySettings
from .notification import NotificationEvent
from .payment import PaymentCapture, PaymentIntent
from .shared import Address, FulfillmentWindow, MarketplaceBaseModel, Money, Timestamped


class OrderState(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    allocated = "allocated"
    fulfilled = "fulfilled"
    cancelled = "cancelled"
    refunded = "refunded"


class OrderPriority(str, Enum):
    standard = "standard"
    express = "express"
    vip = "vip"


class StateTransition(MarketplaceBaseModel):
    from_state: OrderState
    to_state: OrderState
    occurred_at: datetime
    note: str | None = None


class ShipmentLeg(MarketplaceBaseModel):
    leg_id: UUID
    carrier: str
    tracking_code: Annotated[str, Field(pattern=r"^[A-Z0-9]{8,32}$")]
    destination: Address
    promised_window: FulfillmentWindow


class LineDiscount(MarketplaceBaseModel):
    description: str
    amount: Money


class OrderLine(MarketplaceBaseModel):
    variant: CatalogVariant
    quantity: Annotated[int, Field(ge=1, le=50)]
    selected_addons: list[str] = Field(default_factory=list)
    discounts: list[LineDiscount] = Field(default_factory=list)


class OrderEnvelope(Timestamped):
    order_id: UUID
    customer: CustomerProfile
    delivery: DeliverySettings
    items: list[OrderLine]
    payment_intent: PaymentIntent
    captures: list[PaymentCapture] = Field(default_factory=list)
    state_history: list[StateTransition]
    shipments: list[ShipmentLeg]
    notifications: list[NotificationEvent] = Field(default_factory=list)
    priority: OrderPriority = OrderPriority.standard
    gift_message: str | None = None
