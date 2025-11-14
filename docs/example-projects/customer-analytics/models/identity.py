"""Identity & lifecycle models reused across events and segments."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import EmailStr, Field

from .shared import AnalyticsBaseModel, Locale


class LifecycleStage(str, Enum):
    prospect = "prospect"
    activated = "activated"
    churned = "churned"


class LoyaltyProfile(AnalyticsBaseModel):
    user_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    email: EmailStr = "demo@example.com"
    locale: Locale = Locale.en_us
    stage: LifecycleStage = LifecycleStage.activated
    tags: list[str] = Field(default_factory=lambda: ["newsletter", "vip"])
    region: str = Field(default="SE", pattern=r"^[A-Z]{2}$")
