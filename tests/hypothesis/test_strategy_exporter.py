from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from pydantic_fixturegen.hypothesis import strategy_for

pytest.importorskip("hypothesis")
from hypothesis.errors import NonInteractiveExampleWarning  # noqa: E402

from hypothesis import given, settings  # noqa: E402


class Sample(BaseModel):
    name: str = Field(min_length=3, max_length=8)
    age: int = Field(ge=18, le=30)


@given(strategy_for(Sample))
@settings(max_examples=10, deadline=None)
def test_strategy_produces_valid_models(instance: Sample) -> None:
    assert isinstance(instance, Sample)
    assert 18 <= instance.age <= 30
    assert 3 <= len(instance.name) <= 8


class OptionalModel(BaseModel):
    value: str | None


def test_strategy_supports_optional_fields() -> None:
    strategy = strategy_for(OptionalModel, profile="edge")
    with pytest.warns(NonInteractiveExampleWarning):
        example = strategy.example()
    assert isinstance(example, OptionalModel)
