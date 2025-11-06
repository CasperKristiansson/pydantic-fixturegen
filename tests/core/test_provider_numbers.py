from __future__ import annotations

import decimal
import random

import pytest
from pydantic_fixturegen.core.providers import numbers as numbers_mod
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(type_name: str, **kwargs: object) -> FieldSummary:
    return FieldSummary(type=type_name, constraints=FieldConstraints(**kwargs))


def test_generate_numeric_bool_respects_random_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = random.Random()
    sequence = [True, False, True]
    monkeypatch.setattr(rng, "choice", lambda options: sequence.pop(0))

    values = [
        numbers_mod.generate_numeric(_summary("bool"), random_generator=rng) for _ in range(3)
    ]

    assert values == [True, False, True]


def test_generate_numeric_int_constraints() -> None:
    summary = _summary("int", ge=5, lt=8)
    rng = random.Random(0)
    values = {numbers_mod.generate_numeric(summary, random_generator=rng) for _ in range(10)}

    assert values <= {5, 6, 7}
    assert values >= {5}


def test_generate_numeric_float_with_bounds() -> None:
    summary = _summary("float", gt=1.0, le=2.5)
    rng = random.Random(1)
    value = numbers_mod.generate_numeric(summary, random_generator=rng)

    assert 1.0 < value <= 2.5


def test_generate_numeric_decimal_limits_digits() -> None:
    constraints = FieldConstraints(
        ge=1.0,
        le=2.0,
        decimal_places=3,
        max_digits=4,
    )
    summary = FieldSummary(type="decimal", constraints=constraints)
    rng = random.Random(2)

    result = numbers_mod.generate_numeric(summary, random_generator=rng)

    assert isinstance(result, decimal.Decimal)
    assert decimal.Decimal("1.0") <= result <= decimal.Decimal("2.0")
    assert abs(result.as_tuple().exponent) <= 3


def test_generate_numeric_raises_unknown_type() -> None:
    with pytest.raises(ValueError):
        numbers_mod.generate_numeric(_summary("complex"))
