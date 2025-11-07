from __future__ import annotations

import decimal
import random
from dataclasses import dataclass

import pytest
from pydantic_fixturegen.core.config import NumberDistributionConfig
from pydantic_fixturegen.core.providers import numbers
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(type_id: str, **constraints: float) -> FieldSummary:
    data = FieldConstraints()
    for key, value in constraints.items():
        setattr(data, key, value)
    return FieldSummary(type=type_id, constraints=data)


@dataclass
class _OffsetNormal:
    multiplier: float

    def normalvariate(self, mu: float, sigma: float) -> float:  # noqa: D401
        return mu + self.multiplier * sigma


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


def test_generate_numeric_int_with_gt_constraint() -> None:
    summary = _summary("int", gt=2, lt=6)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert 3 <= value <= 5


def test_generate_numeric_decimal_narrow_window_and_digits() -> None:
    constraints = FieldConstraints(
        ge=decimal.Decimal("0.015"),
        le=decimal.Decimal("0.016"),
        decimal_places=2,
        max_digits=2,
    )
    summary = FieldSummary(type="decimal", constraints=constraints)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert value == decimal.Decimal("0.01")


def test_generate_numeric_decimal_gt_lt_constraints() -> None:
    constraints = FieldConstraints(
        gt=decimal.Decimal("1.00"),
        lt=decimal.Decimal("1.02"),
        decimal_places=2,
    )
    summary = FieldSummary(type="decimal", constraints=constraints)
    value = numbers.generate_numeric(summary, random_generator=random.Random(0))
    assert decimal.Decimal("1.00") < value < decimal.Decimal("1.02")


def test_generate_numeric_int_spike_distribution() -> None:
    summary = _summary("int", ge=0, le=100)
    config = NumberDistributionConfig(
        distribution="spike",
        spike_ratio=1.0,
        spike_width_fraction=0.05,
    )
    value = numbers.generate_numeric(
        summary,
        random_generator=random.Random(0),
        number_config=config,
    )
    assert 45 <= value <= 55


def test_generate_numeric_float_spike_distribution() -> None:
    summary = _summary("float", ge=0.0, le=10.0)
    config = NumberDistributionConfig(
        distribution="spike",
        spike_ratio=1.0,
        spike_width_fraction=0.05,
    )
    value = numbers.generate_numeric(
        summary,
        random_generator=random.Random(0),
        number_config=config,
    )
    assert 4.5 <= value <= 5.5


def test_generate_numeric_float_normal_clamps_upper_bound() -> None:
    summary = _summary("float", ge=0.0, le=1.0)
    config = NumberDistributionConfig(distribution="normal", normal_stddev_fraction=0.2)
    value = numbers.generate_numeric(
        summary,
        random_generator=_OffsetNormal(10.0),
        number_config=config,
    )
    assert value == pytest.approx(1.0)


def test_generate_numeric_float_normal_clamps_lower_bound() -> None:
    summary = _summary("float", ge=0.0, le=1.0)
    config = NumberDistributionConfig(distribution="normal", normal_stddev_fraction=0.2)
    value = numbers.generate_numeric(
        summary,
        random_generator=_OffsetNormal(-10.0),
        number_config=config,
    )
    assert value == pytest.approx(0.0)
