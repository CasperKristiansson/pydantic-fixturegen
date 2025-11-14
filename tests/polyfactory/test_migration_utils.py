from __future__ import annotations

import enum
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core.strategies import UnionStrategy
from pydantic_fixturegen.polyfactory_support import migration as migration_mod


def test_translate_field_serializes_plain_values() -> None:
    report = migration_mod._translate_field("field", 3.14, "provider")  # type: ignore[attr-defined]

    assert report.kind == "Value"
    assert report.translation == {"value": 3.14}
    assert report.fixturegen_provider == "provider"


def test_translate_field_reports_unserializable_values() -> None:
    report = migration_mod._translate_field("field", None, None)  # type: ignore[attr-defined]

    assert report.translation is None
    assert report.message == "value cannot be serialized into fixturegen overrides"


def test_describe_strategy_handles_union_and_metadata() -> None:
    union = UnionStrategy(field_name="foo", choices=[], policy="random")
    assert migration_mod.describe_strategy(union) == "union(random)"

    provider_ref = SimpleNamespace(name=None, type_id="slug", format="url")
    heuristic = SimpleNamespace(rule="email_hint", provider_type="string")
    type_default = SimpleNamespace(
        rule=SimpleNamespace(name="fallback"),
        provider=SimpleNamespace(type_id="string"),
    )
    strategy = SimpleNamespace(
        provider_ref=provider_ref,
        provider_name="custom.provider",
        heuristic=heuristic,
        type_default=type_default,
    )

    assert (
        migration_mod.describe_strategy(strategy)
        == "custom.provider [heuristic:email_hint] [default:fallback]"
    )


def test_callable_path_handles_unresolvable_callables() -> None:
    def outer():
        def inner():
            return None

        return inner

    path, label = migration_mod._callable_path(outer())

    assert path is None
    assert "inner" in label


def test_serialize_value_supports_enums_and_nested_structures() -> None:
    class Sample(enum.Enum):
        ONE = 1

    assert migration_mod._serialize_value(Sample.ONE) == 1
    assert migration_mod._serialize_value(["x", Sample.ONE]) == ["x", 1]
    assert migration_mod._serialize_value({"key": ["value"]}) == {"key": ["value"]}
    assert migration_mod._serialize_list([Sample.ONE, "z"]) == [1, "z"]
    assert migration_mod._serialize_mapping({"a": Sample.ONE}) == {"a": 1}


def test_serialize_value_rejects_invalid_keys() -> None:
    with pytest.raises(ValueError):
        migration_mod._serialize_value({"bad": {1: "x"}})

    with pytest.raises(ValueError):
        migration_mod._serialize_value(None)
