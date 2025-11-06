"""Providers for NumPy array generation."""

from __future__ import annotations

import math
import types
from collections.abc import Sequence
from typing import Any, cast

from pydantic_fixturegen.core.config import ArrayConfig
from pydantic_fixturegen.core.schema import FieldSummary

from .registry import ProviderRegistry

__all__ = ["register_numpy_array_providers", "generate_numpy_array"]

_np: types.ModuleType | None
try:  # Optional dependency
    import numpy as _np
except ModuleNotFoundError:  # pragma: no cover - optional extra not installed
    _np = None


def _ensure_numpy_available() -> Any:
    if _np is None:
        raise RuntimeError(
            "NumPy is required for array generation. Install the optional dependency via "
            "`pip install pydantic-fixturegen[numpy]`."
        )
    return cast(Any, _np)


def _select_dtype(allowed: Sequence[str], *, preferred: str | None = None) -> Any:
    np_module = _ensure_numpy_available()
    candidates = list(allowed) if allowed else ["float64"]
    dtype_candidate = preferred if preferred and preferred in candidates else candidates[0]
    try:
        return np_module.dtype(dtype_candidate)
    except TypeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Unsupported NumPy dtype: {dtype_candidate!r}") from exc


def _bounded_shape(
    *,
    rng: Any,
    max_ndim: int,
    max_side: int,
    max_elements: int,
) -> tuple[int, ...]:
    ndim = max(1, min(max_ndim, 5))
    result: list[int] = []
    product = 1

    for _index in range(ndim):
        remaining = max_elements // product
        if remaining < 1:
            break
        side_cap = max(1, min(max_side, remaining))
        size = rng.randint(1, side_cap)
        result.append(size)
        product *= size
        if product >= max_elements:
            break

    if not result:
        result = [1]
    return tuple(result)


def generate_numpy_array(
    summary: FieldSummary,
    *,
    array_config: ArrayConfig,
    numpy_rng: Any | None = None,
    random_generator: Any | None = None,
    **_: Any,
) -> Any:
    """Generate a deterministic NumPy array honoring configured caps."""

    np_module = _ensure_numpy_available()
    if numpy_rng is None:
        raise RuntimeError(
            "NumPy RNG unavailable. Ensure SeedManager.numpy_for is used when NumPy is installed."
        )
    rng = random_generator
    if rng is None:
        raise RuntimeError("random_generator must be supplied for numpy array generation.")

    dtype = _select_dtype(array_config.dtypes, preferred=summary.format)
    shape = _bounded_shape(
        rng=rng,
        max_ndim=array_config.max_ndim,
        max_side=array_config.max_side,
        max_elements=array_config.max_elements,
    )

    if np_module.issubdtype(dtype, np_module.floating):
        data = numpy_rng.random(shape, dtype=dtype)
    elif np_module.issubdtype(dtype, np_module.integer):
        upper = max(2, math.isqrt(array_config.max_elements) * 10)
        data = numpy_rng.integers(low=0, high=upper, size=shape, dtype=dtype)
    elif np_module.issubdtype(dtype, np_module.bool_):
        data = numpy_rng.integers(low=0, high=2, size=shape, dtype=np_module.int8).astype(dtype)
    else:
        data = numpy_rng.random(shape).astype(dtype)

    return data


def register_numpy_array_providers(registry: ProviderRegistry) -> None:
    registry.register(
        "numpy-array",
        generate_numpy_array,
        name="numpy.ndarray",
        metadata={"description": "NumPy array provider"},
    )
