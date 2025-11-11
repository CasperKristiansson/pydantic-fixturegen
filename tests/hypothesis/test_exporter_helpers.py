import datetime as _dt
import decimal
import ipaddress
import pathlib
import uuid
import warnings
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from hypothesis.errors import HypothesisDeprecationWarning, NonInteractiveExampleWarning
from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.strategies import Strategy, UnionStrategy
from pydantic_fixturegen.hypothesis.exporter import (
    _HypothesisStrategyExporter,
    _SecretBytesShim,
    _SecretStrShim,
    strategy_for,
)

from hypothesis import strategies as st

warnings.filterwarnings("ignore", category=HypothesisDeprecationWarning)
WARNING_TYPES = (NonInteractiveExampleWarning, HypothesisDeprecationWarning)


class _DummyGenerator:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def push(self, value: Any) -> None:
        self.values.append(value)

    def generate_one(self, model: type[Any]) -> Any:
        if not self.values:
            return None
        return self.values.pop(0)


@dataclass
class _Payload:
    value: int


class _EmbeddedModel(BaseModel):
    value: int


def _exporter() -> _HypothesisStrategyExporter:
    return _HypothesisStrategyExporter(generator=_DummyGenerator(), profile="typical")


def _describe_type(value: Any) -> str:
    type_ = type(value)
    mro = ", ".join(f"{cls.__module__}.{cls.__qualname__}" for cls in type_.__mro__)
    return f"{type_.__module__}.{type_.__qualname__} (mro={mro})"


def _summary(
    type_id: str,
    *,
    constraints: FieldConstraints | None = None,
    **extra: Any,
) -> FieldSummary:
    return FieldSummary(
        type=type_id,
        constraints=constraints or FieldConstraints(),
        **extra,
    )


def test_optional_strategy_branches() -> None:
    exporter = _exporter()
    always_none = exporter._optional(st.just("x"), 1.2)
    with pytest.warns(WARNING_TYPES):
        assert always_none.example() is None

    never_none = exporter._optional(st.just("x"), -0.5)
    with pytest.warns(WARNING_TYPES):
        assert never_none.example() in {None, "x"}

    mixed = exporter._optional(st.just("value"), 0.5)
    with pytest.warns(WARNING_TYPES):
        assert mixed.example() in {None, "value"}


def test_secret_and_path_strategies_generate_expected_wrappers() -> None:
    exporter = _exporter()
    secret_str = FieldSummary(type="secret-str", constraints=FieldConstraints())
    secret_bytes = FieldSummary(type="secret-bytes", constraints=FieldConstraints())
    file_path = FieldSummary(
        type="path",
        constraints=FieldConstraints(),
        format="file",
    )

    with pytest.warns(WARNING_TYPES):
        str_value = exporter._secret_strategy(secret_str).example()
    with pytest.warns(WARNING_TYPES):
        bytes_value = exporter._secret_strategy(secret_bytes).example()
    with pytest.warns(WARNING_TYPES):
        path_value = exporter._path_strategy(file_path).example()

    from pydantic import SecretBytes, SecretStr  # local import keeps optional dependency lazy

    assert isinstance(
        str_value,
        (SecretStr, _SecretStrShim),
    ), f"secret-str strategy produced {_describe_type(str_value)}"
    assert isinstance(
        bytes_value,
        (SecretBytes, _SecretBytesShim),
    ), f"secret-bytes strategy produced {_describe_type(bytes_value)}"
    assert path_value.suffix in {".json", ".txt", ".log"}


def test_secret_shim_produces_instances() -> None:
    repaired = _SecretStrShim("probe")
    assert isinstance(repaired, SecretStr)
    assert repaired.get_secret_value() == "probe"


def test_collection_and_mapping_strategies_respect_bounds() -> None:
    exporter = _exporter()
    tuple_summary = FieldSummary(
        type="tuple",
        constraints=FieldConstraints(min_length=1, max_length=2),
        item_annotation=int,
    )
    set_summary = FieldSummary(
        type="set",
        constraints=FieldConstraints(),
        item_annotation=str,
    )
    mapping_summary = FieldSummary(
        type="mapping",
        constraints=FieldConstraints(min_length=1, max_length=2),
        item_annotation=str,
    )

    with pytest.warns(WARNING_TYPES):
        tuple_value = exporter._collection_strategy(tuple_summary).example()
    with pytest.warns(WARNING_TYPES):
        set_value = exporter._collection_strategy(set_summary).example()
    with pytest.warns(WARNING_TYPES):
        mapping_value = exporter._mapping_strategy(mapping_summary).example()

    assert isinstance(tuple_value, tuple) and 1 <= len(tuple_value) <= 2
    assert isinstance(set_value, set)
    assert mapping_value and 1 <= len(mapping_value) <= 2


def test_annotation_strategy_handles_literal_and_union() -> None:
    exporter = _exporter()
    literal_strategy = exporter._strategy_for_annotation(Literal["a", "b"])
    union_strategy = exporter._strategy_for_annotation(int | None)
    list_strategy = exporter._strategy_for_annotation(list[int])
    dict_strategy = exporter._strategy_for_annotation(dict[str, int])

    with pytest.warns(WARNING_TYPES):
        assert literal_strategy.example() in {"a", "b"}
    with pytest.warns(WARNING_TYPES):
        union_value = union_strategy.example()
    assert union_value is None or isinstance(union_value, int)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(list_strategy.example(), list)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(dict_strategy.example(), dict)


def test_dataclass_strategy_caches_instances() -> None:
    exporter = _exporter()

    @dataclass
    class Sample:
        value: int

    first = exporter._dataclass_strategy(Sample)
    second = exporter._dataclass_strategy(Sample)
    assert first is second

    with pytest.warns(WARNING_TYPES):
        assert isinstance(first.example(), Sample)


def test_fallback_strategy_uses_generator_value() -> None:
    generator = _DummyGenerator()
    generator.push(SimpleNamespace(field="ok"))
    exporter = _HypothesisStrategyExporter(generator=generator, profile="typical")
    fallback = exporter._fallback_strategy(SimpleNamespace, "field")

    with pytest.warns(WARNING_TYPES):
        assert fallback.example() == "ok"


def test_strategy_for_annotation_handles_dataclass_and_model() -> None:
    exporter = _exporter()

    @dataclass
    class Nested:
        label: str

    result = exporter._strategy_for_annotation(Nested)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(result.example(), Nested)

    def fake_model_strategy(model: type[BaseModel]) -> Any:
        return st.just(model(value=1))

    exporter.model_strategy = lambda model: fake_model_strategy(model)  # type: ignore[assignment]
    model_result = exporter._strategy_for_annotation(_EmbeddedModel)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(model_result.example(), _EmbeddedModel)


def test_base_strategy_handles_core_scalars() -> None:
    exporter = _exporter()
    cases: list[tuple[FieldSummary, Any]] = [
        (_summary("bool"), bool),
        (_summary("int", constraints=FieldConstraints(gt=1, le=8, multiple_of=2)), int),
        (_summary("float", constraints=FieldConstraints(ge=0.5, lt=2.0)), float),
        (
            _summary("decimal", constraints=FieldConstraints(ge=0.1, le=1.0, decimal_places=2)),
            decimal.Decimal,
        ),
        (_summary("string", constraints=FieldConstraints(min_length=1, max_length=3)), str),
        (_summary("bytes", constraints=FieldConstraints(min_length=1, max_length=2)), bytes),
        (_summary("enum", enum_values=["a", "b"]), {"a", "b"}),
        (_summary("email"), str),
        (_summary("url"), str),
        (_summary("uuid"), uuid.UUID),
        (_summary("datetime"), _dt.datetime),
        (_summary("date"), _dt.date),
        (_summary("time"), _dt.time),
        (_summary("ip-address"), (ipaddress.IPv4Address, ipaddress.IPv6Address)),
        (_summary("ip-interface"), (ipaddress.IPv4Interface, ipaddress.IPv6Interface)),
        (_summary("ip-network"), (ipaddress.IPv4Network, ipaddress.IPv6Network)),
        (_summary("path", format="file"), pathlib.Path),
        (_summary("secret-str"), SecretStr),
        (_summary("secret-bytes"), SecretBytes),
        (_summary("list", item_annotation=int), list),
        (_summary("set", item_annotation=int), set),
        (_summary("tuple", item_annotation=int), tuple),
        (_summary("mapping", item_annotation=int), dict),
    ]

    for summary, expected in cases:
        strategy = exporter._base_strategy(
            _EmbeddedModel,
            "value",
            SimpleNamespace(summary=summary),
        )
        with pytest.warns(WARNING_TYPES):
            sample = strategy.example()
        if isinstance(expected, set):
            assert sample in expected
        elif isinstance(expected, tuple):
            assert isinstance(sample, expected)
        else:
            assert isinstance(sample, expected)


def test_union_strategy_combines_choices() -> None:
    exporter = _exporter()
    alpha_summary = _summary("string", constraints=FieldConstraints(min_length=1, max_length=2))
    beta_summary = _summary("int", constraints=FieldConstraints(ge=1, le=5))
    choice_a = Strategy(
        field_name="value",
        summary=alpha_summary,
        annotation=str,
        provider_ref=None,
        provider_name="string",
    )
    choice_b = Strategy(
        field_name="value",
        summary=beta_summary,
        annotation=int,
        provider_ref=None,
        provider_name="int",
    )
    union = UnionStrategy(field_name="value", choices=[choice_a, choice_b], policy="first")
    strategy = exporter._strategy_for_field(_EmbeddedModel, "value", union)

    for _ in range(5):
        with pytest.warns(WARNING_TYPES):
            sample = strategy.example()
        assert isinstance(sample, (str, int))


def test_base_strategy_handles_nested_model_and_dataclass() -> None:
    exporter = _exporter()

    @dataclass
    class Nested:
        payload: str

    summary_model = _summary("model", annotation=_EmbeddedModel)
    summary_dataclass = _summary("dataclass", annotation=Nested)
    exporter.model_strategy = lambda model: st.just(model(value=7))  # type: ignore[assignment]

    model_strategy = exporter._base_strategy(
        _EmbeddedModel,
        "value",
        Strategy(
            field_name="value",
            summary=summary_model,
            annotation=_EmbeddedModel,
            provider_ref=None,
            provider_name="model",
        ),
    )
    dataclass_strategy = exporter._base_strategy(
        _EmbeddedModel,
        "value",
        Strategy(
            field_name="value",
            summary=summary_dataclass,
            annotation=Nested,
            provider_ref=None,
            provider_name="dataclass",
        ),
    )

    with pytest.warns(WARNING_TYPES):
        assert isinstance(model_strategy.example(), _EmbeddedModel)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(dataclass_strategy.example(), Nested)


def test_base_strategy_fallback_errors_when_generator_returns_none() -> None:
    generator = _DummyGenerator()
    exporter = _HypothesisStrategyExporter(generator=generator, profile="typical")
    summary = _summary("custom")
    dummy_strategy = Strategy(
        field_name="value",
        summary=summary,
        annotation=None,
        provider_ref=None,
        provider_name=None,
    )
    fallback = exporter._base_strategy(_EmbeddedModel, "value", dummy_strategy)

    with pytest.raises(RuntimeError), pytest.warns(WARNING_TYPES):
        fallback.example()


def test_strategy_for_annotation_handles_none_and_any() -> None:
    exporter = _exporter()
    none_strategy = exporter._strategy_for_annotation(None)
    any_strategy = exporter._strategy_for_annotation(Any)

    with pytest.warns(WARNING_TYPES):
        assert none_strategy.example() is None
    with pytest.warns(WARNING_TYPES):
        assert any_strategy.example() is None


def test_strategy_for_applies_rng_mode() -> None:
    class DefaultModel(BaseModel):
        value: int = 10

    strat = strategy_for(DefaultModel, rng_mode="system")
    with pytest.warns(WARNING_TYPES):
        assert isinstance(strat.example(), DefaultModel)


def test_model_strategy_uses_cache() -> None:
    class EmptyModel(BaseModel):
        flag: bool = True

    class DummyInstanceGenerator:
        def __init__(self) -> None:
            self.calls = 0

        def _get_model_strategies(self, model: type[BaseModel]) -> dict[str, Any]:
            self.calls += 1
            return {}

    generator = DummyInstanceGenerator()
    exporter = _HypothesisStrategyExporter(generator=generator, profile="typical")
    first = exporter.model_strategy(EmptyModel)
    second = exporter.model_strategy(EmptyModel)

    assert first is second


def test_string_strategy_handles_patterns() -> None:
    exporter = _exporter()
    summary = _summary("string", constraints=FieldConstraints(pattern="^abc$"))
    strategy = exporter._string_strategy(summary)
    with pytest.warns(WARNING_TYPES):
        assert strategy.example() == "abc"


def test_path_strategy_applies_file_suffix() -> None:
    exporter = _exporter()
    summary = _summary("path", constraints=FieldConstraints(), format="file")
    with pytest.warns(WARNING_TYPES):
        sample = exporter._path_strategy(summary).example()
    assert sample.suffix in {".json", ".txt", ".log"}


def test_annotation_strategy_handles_sets_and_tuples() -> None:
    exporter = _exporter()
    set_strategy = exporter._strategy_for_annotation(set[int])
    tuple_strategy = exporter._strategy_for_annotation(tuple[int])
    with pytest.warns(WARNING_TYPES):
        assert isinstance(set_strategy.example(), set)
    with pytest.warns(WARNING_TYPES):
        assert isinstance(tuple_strategy.example(), tuple)


def test_coerce_helpers_handle_missing_bounds() -> None:
    constraints = FieldConstraints()
    assert _HypothesisStrategyExporter._coerce_max_int(constraints) is None
    assert _HypothesisStrategyExporter._coerce_min_float(constraints) is None
