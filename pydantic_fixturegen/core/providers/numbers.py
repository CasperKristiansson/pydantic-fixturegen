"""Numeric providers for ints, floats, decimals, and booleans."""

from __future__ import annotations

import decimal
import random
from typing import Any

from pydantic_fixturegen.core.config import NumberDistributionConfig
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary

INT_DEFAULT_MIN = -10
INT_DEFAULT_MAX = 10
FLOAT_DEFAULT_MIN = -10.0
FLOAT_DEFAULT_MAX = 10.0
DECIMAL_DEFAULT_PLACES = 2


def generate_numeric(
    summary: FieldSummary,
    *,
    random_generator: random.Random | None = None,
    number_config: NumberDistributionConfig | None = None,
) -> Any:
    rng = random_generator or random.Random()
    config = number_config or NumberDistributionConfig()

    if summary.type == "bool":
        return rng.choice([True, False])

    if summary.type == "int":
        return _generate_int(summary.constraints, rng, config)

    if summary.type == "float":
        return _generate_float(summary.constraints, rng, config)

    if summary.type == "decimal":
        return _generate_decimal(summary.constraints, rng, config)

    raise ValueError(f"Unsupported numeric type: {summary.type}")


def register_numeric_providers(registry: ProviderRegistry) -> None:
    registry.register(
        "int",
        generate_numeric,
        name="number.int",
        metadata={"type": "int"},
    )
    registry.register(
        "float",
        generate_numeric,
        name="number.float",
        metadata={"type": "float"},
    )
    registry.register(
        "decimal",
        generate_numeric,
        name="number.decimal",
        metadata={"type": "decimal"},
    )
    registry.register(
        "bool",
        generate_numeric,
        name="number.bool",
        metadata={"type": "bool"},
    )


def _generate_int(
    constraints: FieldConstraints,
    rng: random.Random,
    config: NumberDistributionConfig,
) -> int:
    minimum = INT_DEFAULT_MIN
    maximum = INT_DEFAULT_MAX

    if constraints.ge is not None:
        minimum = int(constraints.ge)
    if constraints.gt is not None:
        minimum = int(constraints.gt) + 1
    if constraints.le is not None:
        maximum = int(constraints.le)
    if constraints.lt is not None:
        maximum = int(constraints.lt) - 1

    if minimum > maximum:
        minimum = maximum

    return _sample_int_with_distribution(rng, minimum, maximum, config)


def _generate_float(
    constraints: FieldConstraints,
    rng: random.Random,
    config: NumberDistributionConfig,
) -> float:
    minimum = FLOAT_DEFAULT_MIN
    maximum = FLOAT_DEFAULT_MAX

    if constraints.ge is not None:
        minimum = float(constraints.ge)
    if constraints.gt is not None:
        minimum = float(constraints.gt) + 1e-6
    if constraints.le is not None:
        maximum = float(constraints.le)
    if constraints.lt is not None:
        maximum = float(constraints.lt) - 1e-6

    if minimum > maximum:
        minimum = maximum

    return _sample_float_with_distribution(rng, minimum, maximum, config)


def _generate_decimal(
    constraints: FieldConstraints,
    rng: random.Random,
    config: NumberDistributionConfig,
) -> decimal.Decimal:
    decimal_places = constraints.decimal_places or DECIMAL_DEFAULT_PLACES
    quantizer = decimal.Decimal(1).scaleb(-decimal_places)

    minimum = decimal.Decimal(FLOAT_DEFAULT_MIN)
    maximum = decimal.Decimal(FLOAT_DEFAULT_MAX)

    if constraints.ge is not None:
        minimum = decimal.Decimal(str(constraints.ge))
    if constraints.gt is not None:
        minimum = decimal.Decimal(str(constraints.gt)) + quantizer
    if constraints.le is not None:
        maximum = decimal.Decimal(str(constraints.le))
    if constraints.lt is not None:
        maximum = decimal.Decimal(str(constraints.lt)) - quantizer

    if minimum > maximum:
        minimum = maximum

    if constraints.max_digits is not None:
        integer_digits = constraints.max_digits - decimal_places
        if integer_digits < 1:
            integer_digits = 1
        limit = decimal.Decimal(10) ** integer_digits - quantizer
        maximum = min(maximum, limit)
        minimum = max(minimum, -limit)

    lower_steps = int((minimum / quantizer).to_integral_value(rounding=decimal.ROUND_CEILING))
    upper_steps = int((maximum / quantizer).to_integral_value(rounding=decimal.ROUND_FLOOR))

    if lower_steps > upper_steps:
        lower_steps = upper_steps

    step = _sample_int_with_distribution(rng, lower_steps, upper_steps, config)
    value = quantizer * decimal.Decimal(step)
    return value.quantize(quantizer, rounding=decimal.ROUND_HALF_UP)


def _sample_int_with_distribution(
    rng: random.Random,
    minimum: int,
    maximum: int,
    config: NumberDistributionConfig,
) -> int:
    if minimum >= maximum:
        return minimum
    if config.distribution == "uniform":
        return rng.randint(minimum, maximum)

    span = maximum - minimum
    center = minimum + span / 2

    if config.distribution == "normal":
        stddev = max(1, int(span * config.normal_stddev_fraction))
        value = int(round(rng.normalvariate(center, stddev)))
        return int(max(minimum, min(maximum, value)))

    # spike distribution
    if rng.random() < config.spike_ratio:
        width = max(1, int(span * config.spike_width_fraction))
        local_min = max(minimum, int(center - width))
        local_max = min(maximum, int(center + width))
        if local_min > local_max:
            local_min = local_max
        return rng.randint(local_min, local_max)
    return rng.randint(minimum, maximum)


def _sample_float_with_distribution(
    rng: random.Random,
    minimum: float,
    maximum: float,
    config: NumberDistributionConfig,
) -> float:
    if minimum >= maximum:
        return minimum
    if config.distribution == "uniform":
        return rng.uniform(minimum, maximum)

    span = maximum - minimum
    center = minimum + span / 2

    if config.distribution == "normal":
        stddev = max(span * config.normal_stddev_fraction, 1e-9)
        value = rng.normalvariate(center, stddev)
        if value < minimum:
            value = minimum
        if value > maximum:
            value = maximum
        return value

    # spike
    if rng.random() < config.spike_ratio:
        width = max(span * config.spike_width_fraction, span * 0.01)
        local_min = max(minimum, center - width)
        local_max = min(maximum, center + width)
        if local_min > local_max:
            local_min = local_max
        return rng.uniform(local_min, local_max)
    return rng.uniform(minimum, maximum)


__all__ = ["generate_numeric", "register_numeric_providers"]
