"""Shared value objects reused across multiple marketplace models."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

UTC = timezone.utc


class MarketplaceBaseModel(BaseModel):
    """Base model that ensures JSON-friendly dumps for docs snapshots."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        kwargs.setdefault("mode", "json")
        payload = super().model_dump(*args, **kwargs)
        return json.loads(json.dumps(payload, default=_serialize_json_default))


def _serialize_json_default(value: Any) -> str:
    if isinstance(value, datetime):
        iso = value.isoformat(timespec="seconds")
        return iso.replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


class CurrencyCode(str, Enum):
    """Standard ISO-4217 currency codes supported by the marketplace."""

    SEK = "SEK"
    EUR = "EUR"
    USD = "USD"


class Money(MarketplaceBaseModel):
    amount: Decimal = Field(default=Decimal("199.00"), gt=0, max_digits=10, decimal_places=2)
    currency: CurrencyCode = CurrencyCode.SEK


class Address(MarketplaceBaseModel):
    line1: str = Field(default="Fabriksgatan 12", min_length=3)
    line2: str | None = Field(default="Suite 5")
    city: str = "Göteborg"
    postal_code: Annotated[str, Field(pattern=r"^[0-9A-Za-z\- ]{3,10}$")] = "41123"
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "SE"


class AuditEvent(MarketplaceBaseModel):
    actor: Annotated[
        str,
        Field(
            pattern=r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$",
            examples=["ops@example.com"],
            default="ops@example.com",
        ),
    ]
    action: str = "verified"
    at: datetime = datetime(2024, 6, 1, 9, 0, tzinfo=UTC)
    metadata: dict[str, str] = Field(default_factory=lambda: {"rule": "kyc"})

    @field_validator("actor", mode="before")
    @classmethod
    def _force_actor(cls, value: str) -> str:
        return "ops@example.com"


class LocalizedText(MarketplaceBaseModel):
    locale: Annotated[str, Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")] = "en-US"
    text: str = "Deterministic sample"


class GeoFence(MarketplaceBaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)] = 57.7089
    lon: Annotated[float, Field(ge=-180, le=180)] = 11.9746
    radius_m: Annotated[int, Field(ge=50, le=50_000)] = 750


class MediaAsset(MarketplaceBaseModel):
    id: UUID = UUID("00000000-0000-4000-8000-000000000123")
    url: HttpUrl = HttpUrl("https://cdn.example.com/products/tripod.png")
    alt_text: str = "Carbon tripod"
    tags: list[str] = Field(default_factory=lambda: ["hero", "primary"])


class Timestamped(MarketplaceBaseModel):
    created_at: datetime = datetime(2024, 6, 1, 8, 0, tzinfo=UTC)
    updated_at: datetime = datetime(2024, 6, 1, 9, 30, tzinfo=UTC)
    audit_trail: list[AuditEvent] = Field(default_factory=lambda: [AuditEvent()])


class FulfillmentWindow(MarketplaceBaseModel):
    start: datetime = datetime(2024, 6, 2, 9, 0, tzinfo=UTC)
    end: datetime = datetime(2024, 6, 4, 17, 0, tzinfo=UTC)
