"""Collection providers for lists, sets, tuples, and mappings."""

from __future__ import annotations

import random
from typing import Any

from faker import Faker

from pydantic_fixturegen.core.collection_utils import sample_collection_length
from pydantic_fixturegen.core.config import CollectionConfig
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary


def generate_collection(
    summary: FieldSummary,
    *,
    faker: Faker | None = None,
    random_generator: random.Random | None = None,
    collection_config: CollectionConfig | None = None,
) -> Any:
    rng = random_generator or random.Random()
    faker = faker or Faker()

    config = collection_config or CollectionConfig()
    length = sample_collection_length(config, summary.constraints, rng)
    if length < 0:
        length = 0
    item_values = [_basic_value(summary.item_type, faker, rng) for _ in range(length)]

    if summary.type == "list":
        return item_values
    if summary.type == "set":
        return set(item_values)
    if summary.type == "tuple":
        return tuple(item_values)
    if summary.type == "mapping":
        return {faker.pystr(min_chars=3, max_chars=6): value for value in item_values}

    raise ValueError(f"Unsupported collection type: {summary.type}")


def register_collection_providers(registry: ProviderRegistry) -> None:
    for collection_type in ("list", "set", "tuple", "mapping"):
        registry.register(
            collection_type,
            generate_collection,
            name=f"collection.{collection_type}",
            metadata={"type": collection_type},
        )


def _basic_value(item_type: str | None, faker: Faker, rng: random.Random) -> Any:
    if item_type == "int":
        return rng.randint(-10, 10)
    if item_type == "float":
        return rng.uniform(-10, 10)
    if item_type == "bool":
        return rng.choice([True, False])
    if item_type == "string" or item_type is None:
        return faker.pystr(min_chars=1, max_chars=8)
    if item_type == "decimal":
        return faker.pydecimal(left_digits=3, right_digits=2)
    if item_type == "model":
        return {}
    return faker.pystr(min_chars=1, max_chars=8)


__all__ = ["generate_collection", "register_collection_providers"]
