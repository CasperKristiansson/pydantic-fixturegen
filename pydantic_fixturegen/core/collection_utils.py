"""Helpers for resolving collection length settings."""

from __future__ import annotations

import random
from dataclasses import replace

from pydantic_fixturegen.core.config import CollectionConfig
from pydantic_fixturegen.core.schema import FieldConstraints


def clamp_collection_config(
    config: CollectionConfig,
    constraints: FieldConstraints,
) -> CollectionConfig:
    min_constraint = constraints.min_length if constraints.min_length is not None else 0
    max_constraint = constraints.max_length
    if max_constraint is not None and max_constraint < min_constraint:
        min_constraint = max_constraint

    min_items = max(config.min_items, min_constraint)
    if max_constraint is None:
        max_items = config.max_items
    else:
        max_items = min(config.max_items, max_constraint)

    if max_items < min_items:
        max_items = min_items

    if min_items == config.min_items and max_items == config.max_items:
        return config
    return replace(config, min_items=min_items, max_items=max_items)


def sample_collection_length(
    config: CollectionConfig,
    constraints: FieldConstraints,
    rng: random.Random,
) -> int:
    bounded = clamp_collection_config(config, constraints)
    minimum = bounded.min_items
    maximum = bounded.max_items
    if maximum <= minimum:
        return minimum

    span = maximum - minimum
    if bounded.distribution == "min-heavy":
        scale = rng.random()
        offset = int((scale * scale) * (span + 1))
        return min(maximum, minimum + offset)
    if bounded.distribution == "max-heavy":
        scale = rng.random()
        offset = int((scale * scale) * (span + 1))
        return max(minimum, maximum - offset)
    return rng.randint(minimum, maximum)


__all__ = ["clamp_collection_config", "sample_collection_length"]
