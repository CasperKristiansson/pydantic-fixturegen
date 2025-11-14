"""Customer-centric models referencing shared value objects."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import EmailStr, Field, HttpUrl

from .shared import Address, GeoFence, MarketplaceBaseModel, Timestamped


class LoyaltyTier(str, Enum):
    bronze = "bronze"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"


class CustomerProfile(Timestamped):
    id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    email: EmailStr = "astrid@example.com"
    primary_phone: Annotated[str, Field(pattern=r"^\+?[0-9]{8,15}$")] = "+46700000000"
    shipping_address: Address = Address()
    billing_address: Address | None = Field(default_factory=lambda: Address(line2="Billing"))
    loyalty_tier: LoyaltyTier = LoyaltyTier.bronze
    marketing_opt_in: bool = True
    tags: list[str] = Field(default_factory=lambda: ["beta-tester", "newsletter"])
    risk_score: Annotated[float, Field(ge=0, le=1)] = 0.42


class Household(MarketplaceBaseModel):
    household_id: UUID = UUID("00000000-0000-4000-8000-000000000999")
    primary_contact: CustomerProfile = CustomerProfile()
    dependents: list[CustomerProfile] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: ["prefers SMS updates"])


class FulfillmentPreference(str, Enum):
    pickup = "pickup"
    delivery = "delivery"
    locker = "locker"


class DeliverySettings(MarketplaceBaseModel):
    preference: FulfillmentPreference = FulfillmentPreference.delivery
    geo_fence: GeoFence | None = Field(default_factory=GeoFence)
    handoff_instructions: str | None = "Leave at reception"


class CustomerPortalSession(MarketplaceBaseModel):
    session_id: UUID = UUID("00000000-0000-4000-8000-000000000abc")
    issued_at: datetime = datetime(2024, 6, 1, 7, 30)
    expires_at: datetime = datetime(2024, 6, 1, 8, 30)
    redirect_url: HttpUrl = HttpUrl("https://app.example.com/account")
    customer: CustomerProfile = CustomerProfile()
