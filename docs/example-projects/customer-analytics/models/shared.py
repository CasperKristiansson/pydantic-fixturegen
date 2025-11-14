"""Shared telemetry primitives for the analytics example."""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsBaseModel(BaseModel):
    """Base class that normalizes datetimes when dumping to JSON."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("mode", "json")
        payload = super().model_dump(*args, **kwargs)
        def _default(value: object) -> str:
            if isinstance(value, datetime):
                return value.isoformat()
            return str(value)

        return json.loads(json.dumps(payload, default=_default))


class Locale(str, Enum):
    en_us = "en_US"
    sv_se = "sv_SE"
    de_de = "de_DE"


class Currency(str, Enum):
    SEK = "SEK"
    EUR = "EUR"


class MetricWindow(AnalyticsBaseModel):
    start: datetime = datetime(2025, 1, 1, 0, 0)
    end: datetime = datetime(2025, 1, 7, 23, 59)


class BaseEvent(AnalyticsBaseModel):
    event_id: UUID = UUID("00000000-0000-4000-8000-000000000000")
    occurred_at: datetime = datetime(2025, 1, 1, 12, 0)
    source: str = Field(default="warehouse", pattern=r"^[a-z_]+$")
    tags: list[str] = Field(default_factory=lambda: ["beta", "cohort:a"])


class Money(AnalyticsBaseModel):
    amount: Annotated[float, Field(ge=0)] = 199.0
    currency: Currency = Currency.SEK
