from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from pydantic_fixturegen.core.providers import ProviderRegistry, create_default_registry
from pydantic_fixturegen.core.strategies import Strategy, StrategyBuilder, UnionStrategy


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class ExampleModel(BaseModel):
    name: str = Field(pattern="^Name", min_length=4)
    age: int | None
    color: Color
    score: int | str


def build_builder(registry: ProviderRegistry | None = None) -> StrategyBuilder:
    registry = registry or create_default_registry(load_plugins=False)
    return StrategyBuilder(
        registry,
        enum_policy="first",
        union_policy="first",
        default_p_none=0.0,
        optional_p_none=0.2,
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
