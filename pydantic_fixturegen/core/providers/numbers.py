"""Numeric providers for ints, floats, decimals, and booleans."""

from __future__ import annotations

import decimal
import random
from typing import Any

from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary

INT_DEFAULT_MIN = -10
INT_DEFAULT_MAX = 10
FLOAT_DEFAULT_MIN = -10.0
FLOAT_DEFAULT_MAX = 10.0
DECIMAL_DEFAULT_PLACES = decimal.Decimal("0.01")


def generate_numeric(
    summary: FieldSummary,
    *,
    random_generator: random.Random | None = None,
) -> Any:
    rng = random_generator or random.Random()

    if summary.type == "bool":
        return rng.choice([True, False])

    if summary.type == "int":
        return _generate_int(summary.constraints, rng)

    if summary.type == "float":
        return _generate_float(summary.constraints, rng)

    if summary.type == "decimal":
        return _generate_decimal(summary.constraints, rng)

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


def _generate_int(constraints: FieldConstraints, rng: random.Random) -> int:
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

    return rng.randint(minimum, maximum)


def _generate_float(constraints: FieldConstraints, rng: random.Random) -> float:
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

    return rng.uniform(minimum, maximum)


def _generate_decimal(constraints: FieldConstraints, rng: random.Random) -> decimal.Decimal:
    minimum = decimal.Decimal(FLOAT_DEFAULT_MIN)
    maximum = decimal.Decimal(FLOAT_DEFAULT_MAX)

    if constraints.ge is not None:
        minimum = decimal.Decimal(str(constraints.ge))
    if constraints.gt is not None:
        minimum = decimal.Decimal(str(constraints.gt)) + decimal.Decimal("0.0001")
    if constraints.le is not None:
        maximum = decimal.Decimal(str(constraints.le))
    if constraints.lt is not None:
        maximum = decimal.Decimal(str(constraints.lt)) - decimal.Decimal("0.0001")

    if minimum > maximum:
        minimum = maximum

    raw = decimal.Decimal(str(rng.uniform(float(minimum), float(maximum))))
    quantizer = _quantizer(constraints)
    return raw.quantize(quantizer, rounding=decimal.ROUND_HALF_UP)


def _quantizer(constraints: FieldConstraints) -> decimal.Decimal:
    if constraints.decimal_places is not None:
        return decimal.Decimal("1").scaleb(-constraints.decimal_places)
    return DECIMAL_DEFAULT_PLACES


__all__ = ["generate_numeric", "register_numeric_providers"]
