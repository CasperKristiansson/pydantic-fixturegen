from __future__ import annotations

import dataclasses
from pathlib import Path

from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.strategies import Strategy
from pydantic_fixturegen.plugins.hookspecs import EmitterContext, hookimpl
from pydantic_fixturegen.plugins.loader import get_plugin_manager, register_plugin
from tests._cli import create_cli_runner

runner = create_cli_runner()


class _StrategyPlugin:
    @hookimpl
    def pfg_modify_strategy(
        self,
        model: type[BaseModel],
        field_name: str,
        strategy: Strategy,
    ) -> Strategy | None:
        if model.__name__ == "User" and field_name == "nickname":
            return dataclasses.replace(strategy, p_none=1.0)
        return None


class _SchemaPlugin:
    def __init__(self) -> None:
        self.called = False

    @hookimpl
    def pfg_emit_artifact(self, kind: str, context: EmitterContext) -> bool:
        if kind != "schema":
            return False
        context.output.write_text("handled", encoding="utf-8")
        self.called = True
        return True


class Address(BaseModel):
    street: str


class User(BaseModel):
    name: str
    nickname: str | None = None
    address: Address


def test_strategy_plugin_modifies_strategy() -> None:
    plugin = _StrategyPlugin()
    manager = get_plugin_manager()
    register_plugin(plugin)

    try:
        generator = InstanceGenerator(config=GenerationConfig(seed=42))
        user = generator.generate_one(User)
        assert isinstance(user, User)
        assert user.nickname is None
    finally:
        manager.unregister(plugin)


def test_emitter_plugin_handles_schema(tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Foo(BaseModel):
    value: int
""",
        encoding="utf-8",
    )

    plugin = _SchemaPlugin()
    manager = get_plugin_manager()
    register_plugin(plugin)

    try:
        output = tmp_path / "schema.json"
        result = runner.invoke(
            cli_app,
            [
                "gen",
                "schema",
                str(module),
                "--out",
                str(output),
                "--json-errors",
            ],
        )

        assert result.exit_code == 0
        assert plugin.called is True
        assert output.read_text(encoding="utf-8") == "handled"
    finally:
        manager.unregister(plugin)
