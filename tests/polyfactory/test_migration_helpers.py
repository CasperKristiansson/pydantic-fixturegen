from __future__ import annotations

from typing import Any

from pydantic_fixturegen.polyfactory_support import migration_helpers as helpers


def sample_use(prefix: str, suffix: str) -> str:
    return f"{prefix}-{suffix}"


def sample_post(name: str, values: dict[str, Any], suffix: str) -> str:
    base = values.get(name)
    return f"{base}-{suffix}" if base else suffix


def test_invoke_use_executes_callable() -> None:
    result = helpers.invoke_use(
        None,
        "tests.polyfactory.test_migration_helpers:sample_use",
        call_args=["foo", "bar"],
    )
    assert result == "foo-bar"


class _Context:
    def __init__(self) -> None:
        self.field_name = "slug"
        self.values = {"slug": "fixture"}


def test_invoke_post_generate_mirrors_polyfactory() -> None:
    context = _Context()
    result = helpers.invoke_post_generate(
        "fixture",
        context,
        "tests.polyfactory.test_migration_helpers:sample_post",
        call_args=["x"],
    )
    assert result == "fixture-x"
