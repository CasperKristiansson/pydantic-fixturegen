"""Telemetry events consumed by downstream segmentation jobs."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, HttpUrl

from .identity import LoyaltyProfile
from .shared import BaseEvent, Money


class PurchaseEvent(BaseEvent):
    profile: LoyaltyProfile = LoyaltyProfile()
    order_id: UUID = UUID("00000000-0000-4000-8000-000000000111")
    amount: Money = Money(amount=499.0)
    sku: str = "SNP-001"
    channel: str = Field(default="web", pattern=r"^[a-z]+$")


class SessionEvent(BaseEvent):
    profile: LoyaltyProfile = LoyaltyProfile(locale="sv_SE")
    entry_page: HttpUrl = HttpUrl("https://app.example.com/dashboard")
    duration_seconds: int = 420
