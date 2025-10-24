from __future__ import annotations

import enum
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator


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
    assert user.nickname is None


class Node(BaseModel):
    name: str
    child: Node | None


Node.model_rebuild()


def test_recursion_guard_depth() -> None:
    config = GenerationConfig(seed=7, max_depth=1)
    generator = InstanceGenerator(config=config)
    node = generator.generate_one(Node)
    assert node is not None
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
    assert isinstance(account, Account)
    assert isinstance(account.profile, Profile)
    assert isinstance(account.user.address, Address)
