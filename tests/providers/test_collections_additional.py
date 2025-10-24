from __future__ import annotations

import random

from pydantic_fixturegen.core.providers import collections
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def test_generate_collection_mapping(tmp_path=None) -> None:
    summary = FieldSummary(
        type="mapping",
        constraints=FieldConstraints(min_length=2, max_length=2),
        item_type="int",
    )
    result = collections.generate_collection(summary, random_generator=random.Random(0))
    assert isinstance(result, dict)
    assert len(result) == 2


def test_collection_length_min_exceeds_max() -> None:
    constraints = FieldConstraints(min_length=4, max_length=2)
    summary = FieldSummary(type="list", constraints=constraints, item_type="string")
    result = collections.generate_collection(summary, random_generator=random.Random(0))
    assert len(result) == 2
