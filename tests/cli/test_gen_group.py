from __future__ import annotations

from pydantic_fixturegen.cli.gen import app as gen_app


def test_gen_app_registers_expected_commands() -> None:
    command_names = {command.name for command in gen_app.registered_commands}
    group_names = {group.name for group in gen_app.registered_groups}

    assert {"json", "schema", "fixtures"} <= command_names
    assert "explain" in group_names
