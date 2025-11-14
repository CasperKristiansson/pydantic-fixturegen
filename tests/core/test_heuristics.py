from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core import heuristics as heuristics_mod
from pydantic_fixturegen.core.heuristics import (
    HeuristicCondition,
    HeuristicMatch,
    HeuristicRegistry,
    HeuristicResult,
    HeuristicRule,
)
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(**kwargs) -> FieldSummary:
    constraints = kwargs.pop("constraints", FieldConstraints())
    return FieldSummary(type=kwargs.pop("type", "string"), constraints=constraints, **kwargs)


def _make_context(**overrides) -> heuristics_mod.HeuristicContext:
    base = dict(
        model=None,
        field_name="Field",
        summary=_summary(constraints=FieldConstraints()),
        field_info=None,
        alias=None,
        path="Field",
        tokens=("field",),
        metadata_tokens=(),
        constraint_pattern="pattern",
    )
    base.update(overrides)
    return heuristics_mod.HeuristicContext(**base)


@pytest.fixture(autouse=True)
def fake_plugin_manager(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    manager = SimpleNamespace(hook=SimpleNamespace(pfg_register_heuristics=lambda **kwargs: None))
    monkeypatch.setattr(heuristics_mod, "get_plugin_manager", lambda: manager)
    return manager


def test_heuristic_match_to_payload() -> None:
    match = HeuristicMatch(
        rule="test",
        description="demo",
        provider_type="string",
        provider_format="email",
        confidence=0.9,
        signals=("s1",),
        provider_kwargs={"hint": True},
    )
    payload = match.to_payload()
    assert payload["signals"] == ["s1"]
    assert payload["provider_format"] == "email"


def test_heuristic_condition_matches_all_constraints() -> None:
    summary = _summary(constraints=FieldConstraints(min_length=3, max_length=3, pattern="foo"))
    context = heuristics_mod.HeuristicContext(
        model=None,
        field_name="ContactEmail",
        summary=summary,
        field_info=None,
        alias=None,
        path="ContactEmail",
        tokens=("contact", "email"),
        metadata_tokens=("sensitive",),
        constraint_pattern="foo",
    )
    condition = HeuristicCondition(
        keywords_all=("contact",),
        keywords_any=("email",),
        metadata_all=("sensitive",),
        metadata_any=("sensitive",),
        name_globs=("contact*",),
        summary_types=("string",),
        constraint_patterns=("foo",),
        length_equals=3,
    )
    result = condition.evaluate(context)
    assert result is not None
    assert any(signal.startswith("keyword") for signal in result.signals)


def test_heuristic_condition_predicate_injects_signals() -> None:
    summary = _summary()
    context = heuristics_mod.HeuristicContext(
        model=None,
        field_name="Name",
        summary=summary,
        field_info=None,
        alias=None,
        path="Name",
        tokens=("name",),
        metadata_tokens=(),
        constraint_pattern=None,
    )

    def predicate(_: heuristics_mod.HeuristicContext) -> HeuristicResult:
        return HeuristicResult(signals=["custom"], provider_kwargs={"fmt": "uuid"}, confidence=0.8)

    condition = HeuristicCondition(predicate=predicate)
    result = condition.evaluate(context)
    assert result is not None
    assert result.provider_kwargs == {"fmt": "uuid"}
    assert result.confidence == 0.8


def test_heuristic_rule_merges_provider_kwargs() -> None:
    summary = _summary()
    context = heuristics_mod.HeuristicContext(
        model=None,
        field_name="slug",
        summary=summary,
        field_info=None,
        alias=None,
        path="slug",
        tokens=("slug",),
        metadata_tokens=(),
        constraint_pattern=None,
    )

    def matcher(_: heuristics_mod.HeuristicContext) -> HeuristicResult:
        return HeuristicResult(signals=["matched"], provider_kwargs={"length": 5}, confidence=0.7)

    rule = HeuristicRule(
        name="slug",
        description="demo",
        provider_type="string",
        provider_format="slug",
        provider_kwargs={"alphabet": "ascii"},
        matcher=matcher,
    )
    match = rule.evaluate(context)
    assert match is not None
    assert match.provider_kwargs == {"alphabet": "ascii", "length": 5}
    assert match.confidence == 0.7


def test_heuristic_rule_without_condition_returns_none() -> None:
    summary = _summary()
    context = heuristics_mod.HeuristicContext(
        model=None,
        field_name="field",
        summary=summary,
        field_info=None,
        alias=None,
        path="field",
        tokens=(),
        metadata_tokens=(),
        constraint_pattern=None,
    )
    rule = HeuristicRule(name="noop", description="", provider_type="string")
    assert rule.evaluate(context) is None


def test_heuristic_registry_registers_and_sorts(fake_plugin_manager: SimpleNamespace) -> None:
    registry = HeuristicRegistry()
    low = HeuristicRule(
        name="low",
        description="",
        provider_type="string",
        priority=1,
        matcher=lambda ctx: HeuristicResult(signals=["low"]),
    )
    high = HeuristicRule(
        name="high",
        description="",
        provider_type="string",
        priority=10,
        matcher=lambda ctx: HeuristicResult(signals=["high"]),
    )
    registry.register(low)
    registry.register(high)
    summary = _summary()
    match = registry.evaluate(model=None, field_name="name", summary=summary, field_info=None)
    assert match is not None
    assert match.rule == "high"
    registry.clear()
    assert (
        registry.evaluate(model=None, field_name="name", summary=summary, field_info=None) is None
    )


def test_heuristic_registry_register_plugin_invokes_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []
    monkeypatch.setattr(heuristics_mod, "register_plugin", lambda plugin: captured.append(plugin))
    hook_calls: list[dict[str, object]] = []

    class DummyManager:
        def __init__(self) -> None:
            self.hook = SimpleNamespace(
                pfg_register_heuristics=lambda **kwargs: hook_calls.append(kwargs)
            )

    manager = DummyManager()
    monkeypatch.setattr(heuristics_mod, "get_plugin_manager", lambda: manager)
    registry = HeuristicRegistry()
    registry.register_plugin("demo")
    assert captured == ["demo"]
    assert hook_calls and hook_calls[0]["registry"] is registry


def test_heuristic_registry_load_entrypoint_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = []
    monkeypatch.setattr(
        heuristics_mod,
        "load_entrypoint_plugins",
        lambda group, force: [object()],
    )

    class DummyManager:
        def __init__(self) -> None:
            self.hook = SimpleNamespace(
                pfg_register_heuristics=lambda **kwargs: loaded.append(kwargs)
            )

    monkeypatch.setattr(heuristics_mod, "get_plugin_manager", lambda: DummyManager())
    registry = HeuristicRegistry()
    registry.load_entrypoint_plugins(force=True)
    assert loaded and loaded[0]["registry"] is registry


def test_build_context_and_helpers() -> None:
    summary = _summary(format="uuid", metadata=("Sensitive",))
    field_info = SimpleNamespace(
        alias="contactEmail",
        metadata=("pii", SimpleNamespace(alias="secret")),
        title="PrimaryContact",
        description="User email",
        json_schema_extra={"format": "email"},
    )

    model_type = type("Model", (), {})
    context = heuristics_mod._build_context(model_type, "ContactEmail", summary, field_info)
    assert "contact" in context.tokens
    assert "secret" in context.metadata_tokens
    assert context.path.endswith("ContactEmail")

    assert heuristics_mod._tokenize_sources(["CamelCaseValue"]) == ("camel", "case", "value")
    assert heuristics_mod._collect_metadata_tokens(["SomeTag", SimpleNamespace(alias="Alias")]) == [
        "some",
        "tag",
        "alias",
    ]
    assert heuristics_mod._match_globs(["FieldName"], ["field*"])
    assert heuristics_mod._length_matches(
        _summary(constraints=FieldConstraints(min_length=2, max_length=2)),
        2,
    )


def test_register_builtin_rules_installs_defaults() -> None:
    registry = HeuristicRegistry()
    heuristics_mod._register_builtin_rules(registry)
    assert any(rule.name == "string-email" for rule in registry._rules)


def test_condition_returns_none_for_summary_type_mismatch() -> None:
    condition = HeuristicCondition(summary_types=("int",))
    assert condition.evaluate(_make_context()) is None


def test_condition_returns_none_for_keyword_requirements() -> None:
    context = _make_context()
    assert HeuristicCondition(keywords_all=("missing",)).evaluate(context) is None
    assert HeuristicCondition(keywords_any=("absent",)).evaluate(context) is None


def test_condition_returns_none_for_metadata_requirements() -> None:
    context = _make_context(metadata_tokens=())
    assert HeuristicCondition(metadata_all=("tag",)).evaluate(context) is None
    assert HeuristicCondition(metadata_any=("tag",)).evaluate(context) is None


def test_condition_returns_none_for_name_glob_and_pattern() -> None:
    context = _make_context(alias=None)
    assert HeuristicCondition(name_globs=("other*",)).evaluate(context) is None
    context = _make_context(constraint_pattern=None)
    assert HeuristicCondition(constraint_patterns=("uuid",)).evaluate(context) is None


def test_condition_returns_none_for_length_and_predicate() -> None:
    summary = _summary(constraints=FieldConstraints(min_length=1, max_length=1))
    context = _make_context(summary=summary)
    assert HeuristicCondition(length_equals=3).evaluate(context) is None
    assert HeuristicCondition(predicate=lambda ctx: None).evaluate(_make_context()) is None


def test_currency_matcher_variants() -> None:
    context = _make_context(tokens=("currency", "code"), constraint_pattern="USD")
    assert heuristics_mod._currency_matcher(context) is not None
    context = _make_context(tokens=("currency",), constraint_pattern="value")
    assert heuristics_mod._currency_matcher(context) is None


def test_country_alpha_matchers() -> None:
    context = _make_context(tokens=("country", "alpha2"))
    assert heuristics_mod._country_alpha2_matcher(context) is not None
    context = _make_context(tokens=("alpha2",))
    assert heuristics_mod._country_alpha2_matcher(context) is None

    context = _make_context(tokens=("country", "alpha3"))
    assert heuristics_mod._country_alpha3_matcher(context) is not None
    context = _make_context(tokens=("country",))
    assert heuristics_mod._country_alpha3_matcher(context) is None


def test_language_matcher_and_pattern_helpers() -> None:
    context = _make_context(tokens=("language",))
    assert heuristics_mod._language_matcher(context) is not None
    context = _make_context(tokens=("code",))
    assert heuristics_mod._language_matcher(context) is None

    assert heuristics_mod._pattern_matches(_make_context(constraint_pattern="ABC"), r"^[A-Z]{3}$")
    assert not heuristics_mod._pattern_matches(_make_context(constraint_pattern=None), r"foo")
    assert heuristics_mod._looks_like_alpha3(_make_context(constraint_pattern="ABC"))
