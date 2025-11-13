from __future__ import annotations

import random

from pydantic_fixturegen.core.collection_utils import (
    clamp_collection_config,
    sample_collection_length,
)
from pydantic_fixturegen.core.config import CollectionConfig
from pydantic_fixturegen.core.schema import FieldConstraints


def test_clamp_collection_config_respects_constraints() -> None:
    config = CollectionConfig(min_items=1, max_items=6, distribution="max-heavy")
    constraints = FieldConstraints(min_length=3, max_length=4)

    bounded = clamp_collection_config(config, constraints)

    assert bounded.min_items == 3
    assert bounded.max_items == 4
    assert bounded.distribution == "max-heavy"


def test_clamp_collection_config_handles_reversed_bounds() -> None:
    config = CollectionConfig(min_items=2, max_items=3)
    constraints = FieldConstraints(min_length=5, max_length=5)

    bounded = clamp_collection_config(config, constraints)

    assert bounded.min_items == 5
    assert bounded.max_items == 5


def test_clamp_collection_config_handles_invalid_constraints() -> None:
    config = CollectionConfig(min_items=1, max_items=5)
    constraints = FieldConstraints(min_length=4, max_length=2)

    bounded = clamp_collection_config(config, constraints)

    assert bounded.min_items == 2
    assert bounded.max_items == 2


def test_sample_collection_length_uniform() -> None:
    config = CollectionConfig(min_items=1, max_items=4, distribution="uniform")
    rng = random.Random(0)

    length = sample_collection_length(config, FieldConstraints(), rng)

    assert length == 4  # deterministic given the seed


def test_sample_collection_length_biases_extremes() -> None:
    constraints = FieldConstraints()

    min_config = CollectionConfig(min_items=1, max_items=5, distribution="min-heavy")
    min_length = sample_collection_length(min_config, constraints, random.Random(0))
    assert min_length == 4

    max_config = CollectionConfig(min_items=1, max_items=5, distribution="max-heavy")
    max_length = sample_collection_length(max_config, constraints, random.Random(0))
    assert max_length == 2
