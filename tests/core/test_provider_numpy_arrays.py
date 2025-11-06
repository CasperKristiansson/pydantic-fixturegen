from __future__ import annotations

import math

import pytest

from pydantic_fixturegen.core.config import ArrayConfig
from pydantic_fixturegen.core.providers import numpy_arrays
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


class _ConstantRandom:
    """Deterministic helper used to control the shape selection."""

    def __init__(self, value: int = 1) -> None:
        self._value = value

    def randint(self, start: int, end: int) -> int:
        return max(start, min(end, self._value))


def _make_summary(format_hint: str | None) -> FieldSummary:
    return FieldSummary(type="numpy.ndarray", constraints=FieldConstraints(), format=format_hint)


def test_numpy_dependency_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(numpy_arrays, "_np", None, raising=False)

    with pytest.raises(RuntimeError, match="NumPy is required"):
        numpy_arrays._ensure_numpy_available()


def test_numpy_rng_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(numpy_arrays, "_np", np, raising=False)
    summary = _make_summary("float32")
    array_config = ArrayConfig(dtypes=("float32",))

    with pytest.raises(RuntimeError, match="NumPy RNG unavailable"):
        numpy_arrays.generate_numpy_array(
            summary,
            array_config=array_config,
            numpy_rng=None,
            random_generator=_ConstantRandom(),
        )


def test_random_generator_required(monkeypatch: pytest.MonkeyPatch) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(numpy_arrays, "_np", np, raising=False)
    summary = _make_summary("float32")
    array_config = ArrayConfig(dtypes=("float32",))

    with pytest.raises(RuntimeError, match="random_generator must be supplied"):
        numpy_arrays.generate_numpy_array(
            summary,
            array_config=array_config,
            numpy_rng=np.random.default_rng(0),
            random_generator=None,
        )


def test_integer_dtype_path(monkeypatch: pytest.MonkeyPatch) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(numpy_arrays, "_np", np, raising=False)
    summary = _make_summary("int32")
    array_config = ArrayConfig(max_elements=16, dtypes=("int32",))

    result = numpy_arrays.generate_numpy_array(
        summary,
        array_config=array_config,
        numpy_rng=np.random.default_rng(1),
        random_generator=_ConstantRandom(value=2),
    )

    assert result.dtype == np.dtype("int32")
    assert result.size <= array_config.max_elements
    assert result.max() < math.isqrt(array_config.max_elements) * 10


def test_boolean_dtype_path(monkeypatch: pytest.MonkeyPatch) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(numpy_arrays, "_np", np, raising=False)
    summary = _make_summary("bool")
    array_config = ArrayConfig(dtypes=("bool",))

    result = numpy_arrays.generate_numpy_array(
        summary,
        array_config=array_config,
        numpy_rng=np.random.default_rng(2),
        random_generator=_ConstantRandom(),
    )

    assert result.dtype == np.dtype("bool")
    assert set(result.flatten()) <= {False, True}


def test_fallback_dtype_path(monkeypatch: pytest.MonkeyPatch) -> None:
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(numpy_arrays, "_np", np, raising=False)
    summary = _make_summary("complex64")
    array_config = ArrayConfig(dtypes=("complex64",))

    result = numpy_arrays.generate_numpy_array(
        summary,
        array_config=array_config,
        numpy_rng=np.random.default_rng(3),
        random_generator=_ConstantRandom(),
    )

    assert result.dtype == np.dtype("complex64")
    assert result.ndim >= 1


def test_bounded_shape_falls_back_to_default() -> None:
    shape = numpy_arrays._bounded_shape(
        rng=_ConstantRandom(),
        max_ndim=3,
        max_side=4,
        max_elements=0,
    )

    assert shape == (1,)
