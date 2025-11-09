from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.overrides import build_field_override_set


class OverrideUser(BaseModel):
    id: int
    token: str | None = None
    alias: str = "anon"
    first: str = "alpha"
    second: str = "beta"
    joined: str | None = None


def _token_factory(context, prefix: str) -> str:  # noqa: ANN001
    return f"{prefix}-{context.model.__name__}"


def _join_post(value: Any, context):  # noqa: ANN001
    return f"{context.values['first']}-{context.values['second']}"


def test_field_override_sets_constant_value() -> None:
    overrides = {
        f"{OverrideUser.__module__}.{OverrideUser.__qualname__}": {
            "token": {"value": "static-token"}
        }
    }
    override_set = build_field_override_set(overrides)
    generator = InstanceGenerator(config=GenerationConfig(seed=3, field_overrides=override_set))

    user = generator.generate_one(OverrideUser)

    assert user is not None
    assert user.token == "static-token"


def test_field_override_factory_uses_callable() -> None:
    overrides = {
        f"{OverrideUser.__module__}.{OverrideUser.__qualname__}": {
            "token": {"factory": f"{__name__}:_token_factory", "factory_args": ["demo"]}
        }
    }
    override_set = build_field_override_set(overrides)
    generator = InstanceGenerator(config=GenerationConfig(seed=7, field_overrides=override_set))

    user = generator.generate_one(OverrideUser)

    assert user is not None
    assert user.token == "demo-OverrideUser"


def test_field_override_ignore_preserves_default() -> None:
    overrides = {
        f"{OverrideUser.__module__}.{OverrideUser.__qualname__}": {"alias": {"ignore": True}}
    }
    override_set = build_field_override_set(overrides)
    generator = InstanceGenerator(config=GenerationConfig(seed=11, field_overrides=override_set))

    user = generator.generate_one(OverrideUser)

    assert user is not None
    assert user.alias == "anon"


def test_field_override_require_without_value_errors() -> None:
    overrides = {
        f"{OverrideUser.__module__}.{OverrideUser.__qualname__}": {"token": {"require": True}}
    }
    override_set = build_field_override_set(overrides)
    generator = InstanceGenerator(config=GenerationConfig(seed=5, field_overrides=override_set))

    with pytest.raises(ConfigError, match="require"):
        generator.generate_one(OverrideUser)


def test_field_override_post_generate_applies_callback() -> None:
    overrides = {
        f"{OverrideUser.__module__}.{OverrideUser.__qualname__}": {
            "first": {"value": "alpha"},
            "second": {"value": "beta"},
            "joined": {
                "value": "",
                "post_generate": f"{__name__}:_join_post",
            },
        }
    }
    override_set = build_field_override_set(overrides)
    generator = InstanceGenerator(config=GenerationConfig(seed=13, field_overrides=override_set))

    user = generator.generate_one(OverrideUser)

    assert user is not None
    assert user.joined == "alpha-beta"
