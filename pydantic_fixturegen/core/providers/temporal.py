"""Temporal providers for datetime, date, and time types."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from faker import Faker

from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary


def generate_temporal(
    summary: FieldSummary,
    *,
    faker: Faker | None = None,
) -> Any:
    faker = faker or Faker()
    type_name = summary.type

    if type_name == "datetime":
        return faker.date_time(tzinfo=datetime.timezone.utc)
    if type_name == "date":
        return faker.date_object()
    if type_name == "time":
        return faker.time_object()

    raise ValueError(f"Unsupported temporal type: {type_name}")


def register_temporal_providers(registry: ProviderRegistry) -> None:
    for temporal_type in ("datetime", "date", "time"):
        registry.register(
            temporal_type,
            generate_temporal,
            name=f"temporal.{temporal_type}",
            metadata={"type": temporal_type},
        )


__all__ = ["generate_temporal", "register_temporal_providers"]
