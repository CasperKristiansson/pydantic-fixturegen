from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, Field
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.field_policies import FieldPolicy
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.strategies import UnionStrategy


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str


class User(BaseModel):
    name: str = Field(pattern="^User", min_length=5)
    age: int
    nickname: str | None
    address: Address
    tags: list[str]
    role: Color
    preference: int | str
    teammates: list[Address]
    contacts: dict[str, Address]


def test_generate_user_instance() -> None:
    generator = InstanceGenerator(config=GenerationConfig(seed=42))
    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert user.address and isinstance(user.address, Address)
    assert user.name.startswith("User")
    assert user.role in (Color.RED, Color.BLUE)
    assert user.preference is not None


def test_optional_none_probability() -> None:
    config = GenerationConfig(seed=1, optional_p_none=1.0)
    generator = InstanceGenerator(config=config)
    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert user.nickname is None


class Node(BaseModel):
    name: str
    child: Node | None


Node.model_rebuild()


def test_recursion_guard_depth() -> None:
    config = GenerationConfig(seed=7, max_depth=1)
    generator = InstanceGenerator(config=config)
    node = generator.generate_one(Node)
    assert isinstance(node, Node)
    assert node.child is None


def test_object_budget_limits() -> None:
    config = GenerationConfig(seed=3, max_objects=1)
    generator = InstanceGenerator(config=config)
    # Address + User requires more than 1 object, expect None
    assert generator.generate_one(User) is None


def test_union_random_policy() -> None:
    config = GenerationConfig(seed=5, union_policy="random")
    generator = InstanceGenerator(config=config)

    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert isinstance(user.preference, (int, str))
    assert isinstance(user.teammates, list)
    assert all(isinstance(member, Address) for member in user.teammates)
    assert isinstance(user.contacts, dict)
    assert all(isinstance(addr, Address) for addr in user.contacts.values())


@dataclass
class Profile:
    username: str
    active: bool


class Account(BaseModel):
    user: User
    profile: Profile


def test_dataclass_field_generation() -> None:
    generator = InstanceGenerator(config=GenerationConfig(seed=11))
    account = generator.generate_one(Account)
    assert account is not None
    assert isinstance(account, Account)
    assert isinstance(account.profile, Profile)
    assert isinstance(account.user.address, Address)


class OptionalItem(BaseModel):
    maybe: str | None


class PolicyWrapper(BaseModel):
    nested: OptionalItem


def test_field_policy_overrides_p_none() -> None:
    pattern = f"{OptionalItem.__module__}.{OptionalItem.__qualname__}.maybe"
    policy = FieldPolicy(pattern=pattern, options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=1,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    instance = generator.generate_one(OptionalItem)
    assert instance is not None
    assert isinstance(instance, OptionalItem)
    assert instance.maybe is not None


def test_field_policy_conflict_raises() -> None:
    pattern1 = f"{OptionalItem.__module__}.*.maybe"
    pattern2 = f"{OptionalItem.__module__}.{OptionalItem.__qualname__}.maybe"
    policies = (
        FieldPolicy(pattern=pattern1, options={"p_none": 0.0}, index=0),
        FieldPolicy(pattern=pattern2, options={"p_none": 1.0}, index=1),
    )
    generator = InstanceGenerator(config=GenerationConfig(field_policies=policies))

    with pytest.raises(ConfigError):
        generator.generate_one(OptionalItem)


def test_field_policy_matches_model_name_alias() -> None:
    policy = FieldPolicy(pattern="OptionalItem.maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=123,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_matches_field_path_alias() -> None:
    policy = FieldPolicy(pattern="PolicyWrapper.nested.maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=321,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_matches_field_name_alias() -> None:
    policy = FieldPolicy(pattern="maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=11,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_regex_pattern_matches() -> None:
    policy = FieldPolicy(
        pattern=f"re:.*{OptionalItem.__qualname__}\\.maybe$",
        options={"p_none": 0.0},
        index=0,
    )
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=17,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_updates_union_strategy() -> None:
    policy = FieldPolicy(
        pattern=f"{User.__qualname__}.preference",
        options={"union_policy": "random", "p_none": 0.0},
        index=0,
    )
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=23,
            field_policies=(policy,),
        )
    )

    strategies = generator._get_model_strategies(User)
    union_strategy = strategies["preference"]
    assert isinstance(union_strategy, UnionStrategy)

    path_stack = getattr(generator, "_path_stack")  # noqa: B009
    make_path_entry = getattr(generator, "_make_path_entry")  # noqa: B009
    path_stack.append(make_path_entry(User, None))
    try:
        apply_field_policies = getattr(generator, "_apply_field_policies")  # noqa: B009
        apply_field_policies("preference", union_strategy)
    finally:
        path_stack.pop()

    assert union_strategy.policy == "random"
    assert all(choice.p_none == 0.0 for choice in union_strategy.choices)


class TemporalModel(BaseModel):
    created_at: datetime.datetime
    birthday: datetime.date
    alarm: datetime.time


def test_time_anchor_produces_deterministic_temporal_values() -> None:
    anchor = datetime.datetime(2025, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc)
    generator = InstanceGenerator(config=GenerationConfig(seed=123, time_anchor=anchor))

    instance = generator.generate_one(TemporalModel)
    assert instance is not None
    assert isinstance(instance, TemporalModel)
    assert instance.created_at == anchor
    assert instance.birthday == anchor.date()
    # allow either naive or aware time depending on anchor tzinfo
    expected_time = anchor.timetz() if anchor.tzinfo else anchor.time()
    assert instance.alarm.isoformat() == expected_time.isoformat()
