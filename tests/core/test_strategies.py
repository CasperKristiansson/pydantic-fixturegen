from __future__ import annotations

import enum

from typing import Any, Annotated

import annotated_types
from pydantic import BaseModel, Field
from pydantic_fixturegen.core.providers import ProviderRegistry, create_default_registry
from pydantic_fixturegen.core.strategies import Strategy, StrategyBuilder, UnionStrategy
from pydantic_fixturegen.core.config import (
    ProviderBundleConfig,
    ProviderDefaultRule,
    ProviderDefaultsConfig,
)


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class ExampleModel(BaseModel):
    name: str = Field(pattern="^Name", min_length=4)
    age: int | None
    color: Color
    score: int | str


class EmailTag:
    pass


def build_builder(
    registry: ProviderRegistry | None = None,
    *,
    provider_defaults: ProviderDefaultsConfig | None = None,
) -> StrategyBuilder:
    registry = registry or create_default_registry(load_plugins=False)
    return StrategyBuilder(
        registry,
        enum_policy="first",
        union_policy="first",
        default_p_none=0.0,
        optional_p_none=0.2,
        provider_defaults=provider_defaults,
    )


def test_build_strategies_for_model() -> None:
    builder = build_builder()
    strategies = builder.build_model_strategies(ExampleModel)

    name_strategy = strategies["name"]
    assert isinstance(name_strategy, Strategy)
    assert name_strategy.summary.type == "string"
    assert name_strategy.provider_ref is not None
    assert name_strategy.provider_ref.type_id == "string"

    age_strategy = strategies["age"]
    assert isinstance(age_strategy, Strategy)
    assert age_strategy.p_none == 0.2

    color_strategy = strategies["color"]
    assert isinstance(color_strategy, Strategy)
    assert color_strategy.summary.type == "enum"
    assert color_strategy.enum_values == [member.value for member in Color]

    score_strategy = strategies["score"]
    assert isinstance(score_strategy, UnionStrategy)
    assert score_strategy.policy == "first"
    assert {choice.summary.type for choice in score_strategy.choices} == {"int", "string"}


def test_union_policy_random() -> None:
    registry = create_default_registry(load_plugins=False)
    builder = StrategyBuilder(registry, union_policy="random")

    class UnionModel(BaseModel):
        value: int | str

    strategies = builder.build_model_strategies(UnionModel)
    strategy = strategies["value"]
    assert isinstance(strategy, UnionStrategy)
    assert strategy.policy == "random"


def test_enum_policy_random() -> None:
    registry = create_default_registry(load_plugins=False)
    builder = StrategyBuilder(registry, enum_policy="random")

    class EnumModel(BaseModel):
        shade: Color

    shade_strategy = builder.build_model_strategies(EnumModel)["shade"]
    assert isinstance(shade_strategy, Strategy)
    assert shade_strategy.enum_policy == "random"


def test_email_field_uses_identifier_provider() -> None:
    registry = create_default_registry(load_plugins=False)
    builder = StrategyBuilder(registry)

    class EmailModel(BaseModel):
        contact_email: str

    email_strategy = builder.build_model_strategies(EmailModel)["contact_email"]
    assert isinstance(email_strategy, Strategy)
    assert email_strategy.provider_ref is not None
    assert email_strategy.provider_ref.type_id == "email"
    assert email_strategy.heuristic is not None
    assert email_strategy.heuristic.rule == "string-email"


def test_heuristics_can_be_disabled() -> None:
    registry = create_default_registry(load_plugins=False)
    builder = StrategyBuilder(registry, heuristics_enabled=False)

    class EmailModel(BaseModel):
        contact_email: str

    email_strategy = builder.build_model_strategies(EmailModel)["contact_email"]
    assert isinstance(email_strategy, Strategy)
    assert email_strategy.provider_ref is not None
    assert email_strategy.provider_ref.type_id == "string"
    assert email_strategy.heuristic is None


def test_provider_defaults_override_heuristics() -> None:
    registry = create_default_registry(load_plugins=False)

    def _custom_email_provider(*_args: Any, **_kwargs: Any) -> str:
        return "override"

    registry.register("custom-email", _custom_email_provider)

    tag_path = f"{EmailTag.__module__}.{EmailTag.__qualname__}"
    provider_defaults = ProviderDefaultsConfig(
        bundles=(ProviderBundleConfig(name="custom_email", provider="custom-email"),),
        rules=(
            ProviderDefaultRule(
                name="email-rule",
                bundle="custom_email",
                summary_types=("string",),
                metadata_any=(tag_path,),
            ),
        ),
    )

    builder = build_builder(registry, provider_defaults=provider_defaults)

    class EmailModel(BaseModel):
        contact_email: Annotated[str, EmailTag()]

    strategy = builder.build_model_strategies(EmailModel)["contact_email"]
    assert isinstance(strategy, Strategy)
    assert strategy.provider_ref is not None
    assert strategy.provider_ref.type_id == "custom-email"
    assert strategy.type_default is not None
    assert strategy.type_default.rule.name == "email-rule"
    assert strategy.heuristic is None


def test_provider_defaults_match_metadata_rules() -> None:
    registry = create_default_registry(load_plugins=False)

    def _custom_string_provider(*_args: Any, **_kwargs: Any) -> str:
        return "meta"

    registry.register("custom-string", _custom_string_provider)

    provider_defaults = ProviderDefaultsConfig(
        bundles=(ProviderBundleConfig(name="minlen", provider="custom-string"),),
        rules=(
            ProviderDefaultRule(
                name="minlen",
                bundle="minlen",
                summary_types=("string",),
                metadata_all=("annotated_types.MinLen",),
            ),
        ),
    )

    builder = build_builder(registry, provider_defaults=provider_defaults)

    class AnnotatedModel(BaseModel):
        value: Annotated[str, annotated_types.MinLen(3)]

    strategy = builder.build_model_strategies(AnnotatedModel)["value"]
    assert isinstance(strategy, Strategy)
    assert strategy.provider_ref is not None
    assert strategy.provider_ref.type_id == "custom-string"
    assert strategy.type_default is not None
    assert strategy.type_default.rule.name == "minlen"
