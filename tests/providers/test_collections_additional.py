from __future__ import annotations

import decimal
import random

from pydantic_fixturegen.core.providers import collections
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


class StubFaker:
    def __init__(self) -> None:
        self._calls = 0

    def pystr(self, **_: object) -> str:  # noqa: ANN003
        self._calls += 1
        return f"stub-{self._calls}"

    def pydecimal(self, **_: object) -> decimal.Decimal:  # noqa: ANN003
        return decimal.Decimal("1.23")


def test_generate_collection_mapping() -> None:
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


def test_generate_collection_set_bool() -> None:
    summary = FieldSummary(
        type="set",
        constraints=FieldConstraints(min_length=2, max_length=2),
        item_type="bool",
    )
    result = collections.generate_collection(
        summary,
        faker=StubFaker(),
        random_generator=random.Random(1),
    )
    assert isinstance(result, set)
    assert result <= {True, False}


def test_generate_collection_tuple_decimal() -> None:
    summary = FieldSummary(
        type="tuple",
        constraints=FieldConstraints(min_length=1, max_length=1),
        item_type="decimal",
    )
    result = collections.generate_collection(
        summary,
        faker=StubFaker(),
        random_generator=random.Random(0),
    )
    assert result == (decimal.Decimal("1.23"),)


def test_generate_collection_model_items() -> None:
    summary = FieldSummary(
        type="list",
        constraints=FieldConstraints(min_length=1, max_length=1),
        item_type="model",
    )
    result = collections.generate_collection(
        summary,
        faker=StubFaker(),
        random_generator=random.Random(0),
    )
    assert result == [{}]


def test_generate_collection_unknown_item_type_falls_back() -> None:
    summary = FieldSummary(
        type="list",
        constraints=FieldConstraints(min_length=1, max_length=1),
        item_type="custom",
    )
    faker = StubFaker()
    result = collections.generate_collection(
        summary,
        faker=faker,
        random_generator=random.Random(0),
    )
    assert result == ["stub-1"]
