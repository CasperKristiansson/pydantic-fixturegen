from __future__ import annotations

import decimal
import random

import pytest
from pydantic_fixturegen.core.providers import numbers
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(type_id: str, **constraints: float) -> FieldSummary:
    data = FieldConstraints()
    for key, value in constraints.items():
        setattr(data, key, value)
    return FieldSummary(type=type_id, constraints=data)


def test_generate_numeric_bool() -> None:
    summary = _summary("bool")
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert value in {True, False}


def test_generate_numeric_int_bounds() -> None:
    summary = _summary("int", ge=5, lt=5)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert value == 4


def test_generate_numeric_float_adjusts_exclusive() -> None:
    summary = _summary("float", gt=1.0, lt=1.0)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert pytest.approx(value, rel=1e-6) == pytest.approx(1.0 - 1e-6)


def test_generate_numeric_decimal_quantize() -> None:
    constraints = FieldConstraints(ge=1.2, decimal_places=2)
    summary = FieldSummary(type="decimal", constraints=constraints)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert isinstance(value, decimal.Decimal)
    assert value.as_tuple().exponent == -2


def test_generate_numeric_unsupported() -> None:
    summary = _summary("custom")
    with pytest.raises(ValueError):
        numbers.generate_numeric(summary)


def test_generate_numeric_float_bounds_adjustment() -> None:
    summary = _summary("float", ge=1.5, lt=1.6)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert 1.5 <= value < 1.6


def test_generate_numeric_decimal_min_greater_than_max() -> None:
    constraints = FieldConstraints(ge=5.0, le=1.0)
    summary = FieldSummary(type="decimal", constraints=constraints)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert value == decimal.Decimal("1")
