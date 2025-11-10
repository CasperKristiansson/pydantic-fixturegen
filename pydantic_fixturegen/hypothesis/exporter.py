"""Hypothesis strategy exporter leveraging pydantic-fixturegen metadata."""

from __future__ import annotations

import dataclasses
import dataclasses as _dataclasses
import decimal
import importlib
import ipaddress
import math
import pathlib
import string
import types
import warnings
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.seed import RNGModeLiteral
from pydantic_fixturegen.core.strategies import Strategy, StrategyResult, UnionStrategy

# isort: off
if TYPE_CHECKING:  # pragma: no cover - typing only
    from hypothesis import strategies as st
    from hypothesis.strategies import SearchStrategy as HypothesisSearchStrategy
else:  # pragma: no cover - runtime import
    HypothesisSearchStrategy = Any  # type: ignore[assignment]
    try:
        from hypothesis import strategies as st
    except ImportError:
        st = None  # type: ignore[assignment]
# isort: on

StrategyProfileLiteral = Literal["typical", "edge", "adversarial"]

_UNION_TYPES: set[Any] = {Union}
UnionType = getattr(types, "UnionType", None)
if UnionType is not None:  # pragma: no cover - py < 3.10 fallback
    _UNION_TYPES.add(UnionType)


def strategy_for(
    model: type[BaseModel],
    *,
    generation_config: GenerationConfig | None = None,
    profile: StrategyProfileLiteral = "typical",
    rng_mode: RNGModeLiteral | None = None,
) -> HypothesisSearchStrategy[BaseModel]:
    """Return a Hypothesis strategy that emits instances of ``model``.

    The strategy mirrors provider metadata used by the fixture engine. For unsupported
    field types, the exporter falls back to sampling from the configured instance
    generator, ensuring coverage even if shrinkability is limited.
    """

    if st is None:  # pragma: no cover - optional dependency guard
        raise RuntimeError(
            "Hypothesis is not installed. Install the 'hypothesis' extra via "
            "`pip install pydantic-fixturegen[hypothesis]`."
        )

    config = dataclasses.replace(generation_config or GenerationConfig())
    if rng_mode is not None:
        config.rng_mode = rng_mode
    generator = InstanceGenerator(config=config)
    exporter = _HypothesisStrategyExporter(generator=generator, profile=profile)
    return exporter.model_strategy(model)


class _HypothesisStrategyExporter:
    _PROFILE_BOUNDS: Mapping[StrategyProfileLiteral, tuple[int, int]] = {
        "typical": (0, 3),
        "edge": (0, 1),
        "adversarial": (0, 0),
    }

    def __init__(self, *, generator: InstanceGenerator, profile: StrategyProfileLiteral) -> None:
        self.generator = generator
        self._model_cache: dict[type[Any], HypothesisSearchStrategy[Any]] = {}
        self._dataclass_cache: dict[type[Any], HypothesisSearchStrategy[Any]] = {}
        self._collection_bounds = self._PROFILE_BOUNDS.get(profile, self._PROFILE_BOUNDS["typical"])

    # ------------------------------------------------------------------ public API
    def model_strategy(self, model: type[BaseModel]) -> HypothesisSearchStrategy[BaseModel]:
        if model in self._model_cache:
            return self._model_cache[model]

        def factory() -> HypothesisSearchStrategy[BaseModel]:
            strategies = self.generator._get_model_strategies(model)
            field_strategies: dict[str, HypothesisSearchStrategy[Any]] = {}
            for field_name, field_strategy in strategies.items():
                field_strategies[field_name] = self._strategy_for_field(
                    model,
                    field_name,
                    field_strategy,
                )
            return st.builds(model, **field_strategies)

        deferred = st.deferred(factory)
        self._model_cache[model] = deferred
        return deferred

    # ------------------------------------------------------------------ conversion helpers
    def _strategy_for_field(
        self,
        model_type: type[Any],
        field_name: str,
        strategy: StrategyResult,
    ) -> HypothesisSearchStrategy[Any]:
        if isinstance(strategy, UnionStrategy):
            options = [
                self._strategy_for_field(model_type, field_name, choice)
                for choice in strategy.choices
            ]
            return st.one_of(*options)

        base = self._base_strategy(model_type, field_name, strategy)
        if strategy.summary.is_optional:
            return self._optional(base, strategy.p_none)
        return base

    def _base_strategy(
        self,
        model_type: type[Any],
        field_name: str,
        strategy: Strategy,
    ) -> HypothesisSearchStrategy[Any]:
        summary = strategy.summary
        type_id = summary.type

        if type_id == "bool":
            return st.booleans()
        if type_id == "int":
            return self._int_strategy(summary)
        if type_id == "float":
            return self._float_strategy(summary)
        if type_id == "decimal":
            return self._decimal_strategy(summary)
        if type_id == "string":
            return self._string_strategy(summary)
        if type_id == "bytes":
            return self._bytes_strategy(summary)
        if type_id == "enum" and summary.enum_values:
            return st.sampled_from(summary.enum_values)
        if type_id == "email":
            return st.from_regex(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", fullmatch=True)
        if type_id == "url":
            return st.from_regex(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=-]+", fullmatch=True)
        if type_id == "uuid":
            return st.uuids()
        if type_id == "datetime":
            return st.datetimes()
        if type_id == "date":
            return st.dates()
        if type_id == "time":
            return st.times()
        if type_id == "ip-address":
            return st.ip_addresses()
        if type_id == "ip-interface":
            return self._ip_interface_strategy()
        if type_id == "ip-network":
            return self._ip_network_strategy()
        if type_id == "path":
            return self._path_strategy(summary)
        if type_id in {"secret-str", "secret-bytes"}:
            return self._secret_strategy(summary)
        if type_id in {"list", "set", "tuple"}:
            return self._collection_strategy(summary)
        if type_id == "mapping":
            return self._mapping_strategy(summary)
        if type_id == "model" and summary.annotation is not None:
            nested = summary.annotation
            if isinstance(nested, type) and issubclass(nested, BaseModel):
                return self.model_strategy(nested)
        if type_id == "dataclass" and summary.annotation is not None:
            return self._dataclass_strategy(summary.annotation)

        return self._fallback_strategy(model_type, field_name)

    # ------------------------------------------------------------------ scalar helpers
    def _int_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[int]:
        cons = summary.constraints
        min_value = self._coerce_min_int(cons)
        max_value = self._coerce_max_int(cons)
        base = st.integers(min_value=min_value, max_value=max_value)
        multiple = cons.multiple_of
        if multiple and multiple != 0:
            step = int(multiple)
            start = math.ceil((min_value or 0) / step)
            stop = math.floor((max_value or start + 10 * step) / step)
            base = st.integers(min_value=start, max_value=stop).map(lambda idx: idx * step)
        return base

    def _float_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[float]:
        cons = summary.constraints
        return st.floats(
            min_value=self._coerce_min_float(cons),
            max_value=self._coerce_max_float(cons),
            allow_nan=False,
            allow_infinity=False,
        )

    def _decimal_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[decimal.Decimal]:
        cons = summary.constraints
        places = cons.decimal_places
        return st.decimals(
            min_value=self._coerce_min_float(cons),
            max_value=self._coerce_max_float(cons),
            allow_nan=False,
            places=places,
        )

    def _string_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[str]:
        cons = summary.constraints
        if cons.pattern:
            return st.from_regex(cons.pattern, fullmatch=True)
        return st.text(
            min_size=cons.min_length or 0,
            max_size=cons.max_length,
        )

    def _bytes_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[bytes]:
        cons = summary.constraints
        return st.binary(min_size=cons.min_length or 0, max_size=cons.max_length)

    def _secret_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[Any]:
        if summary.type == "secret-str":
            return self._string_strategy(summary).map(_build_secret_str)
        return self._bytes_strategy(summary).map(_build_secret_bytes)

    def _path_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[pathlib.Path]:
        min_size, max_size = 1, max(1, self._collection_bounds[1] or 3)
        alphabet = string.ascii_lowercase + string.digits + "_-"
        segment = st.text(alphabet=alphabet, min_size=1, max_size=8)
        base = st.lists(segment, min_size=min_size, max_size=max_size).map(
            lambda parts: pathlib.Path("/").joinpath(*parts)
        )
        if summary.format == "file":
            suffix = st.sampled_from([".json", ".txt", ".log"])
            base = st.tuples(base, suffix).map(lambda payload: payload[0].with_suffix(payload[1]))
        return base

    def _ip_interface_strategy(self) -> HypothesisSearchStrategy[Any]:
        return st.tuples(
            st.ip_addresses(),
            st.integers(min_value=0, max_value=32),
        ).map(lambda data: ipaddress.ip_interface(f"{data[0]}/{data[1]}"))

    def _ip_network_strategy(self) -> HypothesisSearchStrategy[Any]:
        return st.tuples(
            st.ip_addresses(),
            st.integers(min_value=0, max_value=32),
        ).map(lambda data: ipaddress.ip_network(f"{data[0]}/{data[1]}", strict=False))

    # ------------------------------------------------------------------ collections
    def _collection_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[Any]:
        min_size = summary.constraints.min_length
        max_size = summary.constraints.max_length
        default_min, default_max = self._collection_bounds
        min_bound = min_size if min_size is not None else default_min
        max_bound = max_size if max_size is not None else default_max
        item_strategy = self._strategy_for_annotation(summary.item_annotation)
        if summary.type == "list":
            return st.lists(item_strategy, min_size=min_bound, max_size=max_bound)
        if summary.type == "set":
            return st.sets(item_strategy, min_size=min_bound, max_size=max_bound)
        return st.lists(item_strategy, min_size=min_bound, max_size=max_bound).map(tuple)

    def _mapping_strategy(self, summary: FieldSummary) -> HypothesisSearchStrategy[dict[str, Any]]:
        min_size = summary.constraints.min_length or 0
        max_size = summary.constraints.max_length or self._collection_bounds[1]
        keys = st.text(min_size=1, max_size=8)
        values = self._strategy_for_annotation(summary.item_annotation)
        return st.dictionaries(keys, values, min_size=min_size, max_size=max_size)

    def _dataclass_strategy(self, cls: type[Any]) -> HypothesisSearchStrategy[Any]:
        if cls in self._dataclass_cache:
            return self._dataclass_cache[cls]

        kwargs = {
            field.name: self._strategy_for_annotation(field.type)
            for field in _dataclasses.fields(cls)
        }
        strat = st.builds(cls, **kwargs)
        self._dataclass_cache[cls] = strat
        return strat

    # ------------------------------------------------------------------ fallbacks
    def _fallback_strategy(
        self,
        model_type: type[Any],
        field_name: str,
    ) -> HypothesisSearchStrategy[Any]:
        def build_value() -> Any:
            instance = self.generator.generate_one(model_type)
            if instance is None:
                raise RuntimeError(f"Failed to generate instance for {model_type!r}")
            return getattr(instance, field_name)

        return st.builds(build_value)

    # ------------------------------------------------------------------ annotation helpers
    def _strategy_for_annotation(self, annotation: Any) -> HypothesisSearchStrategy[Any]:
        if annotation is None:
            return st.none()
        if annotation is Any:
            return st.none()

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin in {list, set, tuple}:
            element = args[0] if args else Any
            element_strategy = self._strategy_for_annotation(element)
            min_size, max_size = self._collection_bounds
            base = st.lists(element_strategy, min_size=min_size, max_size=max_size)
            if origin is set:
                return base.map(set)
            if origin is tuple:
                return base.map(tuple)
            return base

        if origin is dict and args:
            value_annotation = args[1] if len(args) > 1 else Any
            return st.dictionaries(
                st.text(min_size=1, max_size=8),
                self._strategy_for_annotation(value_annotation),
                min_size=self._collection_bounds[0],
                max_size=self._collection_bounds[1],
            )

        if origin is Literal and args:
            return st.sampled_from(args)

        if origin in _UNION_TYPES and args:
            non_none = [arg for arg in args if arg is not type(None)]
            if not non_none:
                return st.none()
            base = self._strategy_for_annotation(non_none[0])
            allows_none = len(non_none) != len(args)
            return self._optional(base, 0.5) if allows_none else base

        if isinstance(annotation, type):
            if issubclass(annotation, BaseModel):
                return self.model_strategy(annotation)
            if _dataclasses.is_dataclass(annotation):
                return self._dataclass_strategy(annotation)

        try:
            return st.from_type(annotation)
        except Exception:  # pragma: no cover - fallback path
            return st.just(None)

    # ------------------------------------------------------------------ optionals
    def _optional(
        self,
        base: HypothesisSearchStrategy[Any],
        p_none: float,
    ) -> HypothesisSearchStrategy[Any]:
        if p_none >= 1.0:
            return st.none()
        if p_none <= 0.0:
            return st.one_of(st.none(), base)

        @st.composite
        def optional(draw: Any) -> Any:
            choice = draw(st.integers(min_value=0, max_value=10_000))
            if choice <= int(p_none * 10_000):
                return None
            return draw(base)

        return optional()

    # ------------------------------------------------------------------ constraint helpers
    @staticmethod
    def _coerce_min_int(constraints: FieldConstraints) -> int | None:
        if constraints.gt is not None:
            return math.floor(constraints.gt) + 1
        if constraints.ge is not None:
            return math.floor(constraints.ge)
        return None

    @staticmethod
    def _coerce_max_int(constraints: FieldConstraints) -> int | None:
        if constraints.lt is not None:
            return math.ceil(constraints.lt) - 1
        if constraints.le is not None:
            return math.floor(constraints.le)
        return None

    @staticmethod
    def _coerce_min_float(constraints: FieldConstraints) -> float | None:
        if constraints.gt is not None:
            return math.nextafter(constraints.gt, math.inf)
        return constraints.ge

    @staticmethod
    def _coerce_max_float(constraints: FieldConstraints) -> float | None:
        if constraints.lt is not None:
            return math.nextafter(constraints.lt, -math.inf)
        return constraints.le


def _build_secret_str(value: str) -> Any:
    return _SecretStrShim(value)


def _build_secret_bytes(value: bytes) -> Any:
    return _SecretBytesShim(value)


_SECRET_MODULE_NAMES: tuple[str, ...]
_module_names: list[str] = [
    "pydantic",
    "pydantic.types",
    "pydantic.v1",
    "pydantic.v1.types",
    "pydantic_core._pydantic_core",
]
_SECRET_MODULE_NAMES = tuple(_module_names)


def _import_secret_module(module_name: str) -> types.ModuleType | None:
    try:
        if module_name.startswith("pydantic.v1"):
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=(
                        "Core Pydantic V1 functionality isn't compatible with "
                        "Python 3.14 or greater."
                    ),
                    category=UserWarning,
                )
                return importlib.import_module(module_name)
        return importlib.import_module(module_name)
    except ImportError:  # pragma: no cover - optional dependency layout
        return None


def _secret_classes(attr: str) -> tuple[type[Any], ...]:
    classes: list[type[Any]] = []
    for module_name in _SECRET_MODULE_NAMES:
        module = _import_secret_module(module_name)
        if module is None:
            continue
        candidate = getattr(module, attr, None)
        if isinstance(candidate, type) and candidate not in classes:
            classes.append(candidate)
    if not classes:
        raise RuntimeError(f"Unable to locate {attr} in Pydantic modules.")
    return tuple(classes)


_SECRET_STR_BASES = _secret_classes("SecretStr")
_SECRET_BYTES_BASES = _secret_classes("SecretBytes")
_SECRET_STR_CLS: type[Any] = _SECRET_STR_BASES[0]
_SECRET_BYTES_CLS: type[Any] = _SECRET_BYTES_BASES[0]


def _pin_secret_alias(attr: str, cls: type[Any]) -> None:
    for module_name in _SECRET_MODULE_NAMES:
        module = _import_secret_module(module_name)
        if module is None:
            continue
        current = getattr(module, attr, None)
        if current is not cls:
            setattr(module, attr, cls)


_pin_secret_alias("SecretStr", _SECRET_STR_CLS)
_pin_secret_alias("SecretBytes", _SECRET_BYTES_CLS)


class _SecretStrShim(*_SECRET_STR_BASES):  # type: ignore[misc]
    def __new__(cls, secret_value: Any) -> Any:
        instance = object.__new__(cls)
        object.__setattr__(instance, "_secret_value", secret_value)
        return instance

    def __init__(self, secret_value: Any) -> None:
        pass


class _SecretBytesShim(*_SECRET_BYTES_BASES):  # type: ignore[misc]
    def __new__(cls, secret_value: Any) -> Any:
        instance = object.__new__(cls)
        object.__setattr__(instance, "_secret_value", secret_value)
        return instance

    def __init__(self, secret_value: Any) -> None:
        pass


_SecretStrShim.__module__ = _SECRET_STR_CLS.__module__
_SecretBytesShim.__module__ = _SECRET_BYTES_CLS.__module__
