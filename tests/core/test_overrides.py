from __future__ import annotations

import random

import pytest
from faker import Faker
from pydantic_fixturegen.core import overrides as overrides_mod


def sample_factory(context: overrides_mod.FieldOverrideContext, prefix: str) -> str:
    return f"{prefix}:{context.field_name}"


def sample_post(value: str, context: overrides_mod.FieldOverrideContext, suffix: str) -> str:
    return f"{value}-{suffix}"


NON_CALLABLE = "static"


def _context() -> overrides_mod.FieldOverrideContext:
    return overrides_mod.FieldOverrideContext(
        model=dict,
        field_name="name",
        alias=None,
        summary=None,
        faker=Faker(),
        random=random.Random(0),
        values={},
        path="Model.name",
    )


def test_field_override_resolves_factory_and_post(monkeypatch: pytest.MonkeyPatch) -> None:
    override = overrides_mod.FieldOverride(
        factory="tests.core.test_overrides:sample_factory",
        factory_args=("pref",),
        post_generate="tests.core.test_overrides:sample_post",
        post_args=("done",),
    )

    context = _context()
    value = override.resolve_value(context)
    assert value == "pref:name"
    transformed = override.apply_post(value, context)
    assert transformed == "pref:name-done"


def test_field_override_missing_value_errors() -> None:
    override = overrides_mod.FieldOverride()
    with pytest.raises(overrides_mod.ConfigError):
        override.resolve_value(_context())


def test_field_override_apply_post_noop() -> None:
    override = overrides_mod.FieldOverride(value="data")
    context = _context()
    assert override.apply_post(override.resolve_value(context), context) == "data"


def test_pattern_matching_prefers_specificity() -> None:
    exact = overrides_mod._Pattern("models.User", 0)
    regex = overrides_mod._Pattern("re:.*", 1)
    assert exact.matches("models.User")
    assert not exact.matches("models.Account")
    assert regex.matches("anything")
    assert not exact.matches(None)
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._Pattern("", 0)


def test_field_override_set_resolves_aliases() -> None:
    mapping = {
        "models.User": {
            "id": {"value": 1},
            "alias_*": {"ignore": True},
        }
    }

    override_set = overrides_mod.build_field_override_set(mapping)
    assert override_set is not None

    id_override = override_set.resolve(model_keys=("models.User",), field_name="id")
    assert id_override and id_override.value == 1

    alias_override = override_set.resolve(
        model_keys=("models.User",),
        field_name="email",
        aliases=("alias_email",),
    )
    assert alias_override and alias_override.ignore


def test_build_field_override_set_validates_inputs() -> None:
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod.build_field_override_set({"models.User": {"field": 1}})

    assert overrides_mod.build_field_override_set({}) is None

    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._build_field_override("models.User", "field", {"value": 1, "factory": "x"})

    override = overrides_mod._build_field_override(
        "models.User",
        "field",
        {"provider_kwargs": {"seed": 1}, "provider": "string"},
    )
    assert override.provider == "string"

    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod.build_field_override_set({"models.User": 123})
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._build_field_override(
            "models.User",
            "field",
            {"ignore": True, "value": 1},
        )


def test_coercion_helpers() -> None:
    assert overrides_mod._ensure_mapping({"key": "value"}, "label")["key"] == "value"
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._ensure_mapping({1: "value"}, "label")
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._ensure_mapping([], "label")

    assert overrides_mod._coerce_tuple([1, 2], "label") == (1, 2)
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_tuple("not-seq", "label")

    assert overrides_mod._coerce_optional_str(" data ", label="value") == "data"
    assert overrides_mod._coerce_optional_str(None, label="value") is None
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_optional_str(123, label="value")

    assert overrides_mod._coerce_optional_float("0.25") == 0.25
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_optional_float("not-num")
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_optional_float("2")

    assert overrides_mod._coerce_policy("first", {"first", "random"}, "label") == "first"
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_policy("other", {"first"}, "label")

    assert overrides_mod._coerce_bool("yes")
    assert not overrides_mod._coerce_bool("no")
    assert not overrides_mod._coerce_bool(None)
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._coerce_bool("unknown")


def test_load_callable_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    func = overrides_mod._load_callable("tests.core.test_overrides:sample_factory")
    context = _context()
    assert func(context, "prefix") == "prefix:name"

    dotted = overrides_mod._load_callable("tests.core.test_overrides.sample_post")
    assert dotted("value", context, "sfx") == "value-sfx"

    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._load_callable("")
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._load_callable("tests.core.test_overrides:missing")
    with pytest.raises(overrides_mod.ConfigError):
        overrides_mod._load_callable("tests.core.test_overrides:NON_CALLABLE")


def test_field_override_affects_strategy_flag() -> None:
    override = overrides_mod.FieldOverride(provider="string", p_none=0.5)
    assert override.affects_strategy is True


def test_override_set_describe_returns_detached_data() -> None:
    mapping = {"models.User": {"name": {"value": "guest"}}}
    override_set = overrides_mod.build_field_override_set(mapping)
    assert override_set is not None
    descriptors = override_set.describe()
    assert descriptors[0].model_pattern == "models.User"
    assert descriptors[0].field_pattern == "name"


def test_model_entry_and_field_resolution_gaps() -> None:
    override = overrides_mod.FieldOverride(value="data")
    entry = overrides_mod._ModelEntry(
        matcher=overrides_mod._Pattern("models.User", 0),
        fields=(
            overrides_mod._FieldEntry(
                matcher=overrides_mod._Pattern("name", 0),
                override=override,
            ),
        ),
    )
    assert entry.resolve(("models.User",), "name", None) is not None
    assert entry.resolve(("models.Account",), "name", None) is None

    override_set = overrides_mod.FieldOverrideSet((entry,))
    assert override_set.resolve(model_keys=("models.Account",), field_name="name") is None
