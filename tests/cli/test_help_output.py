from __future__ import annotations

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def test_persist_help_lists_options() -> None:
    result = runner.invoke(cli_app, ["persist", "--help"])
    assert result.exit_code == 0
    assert "--handler" in result.stdout
    assert "--batch-size" in result.stdout


def test_polyfactory_help_lists_subcommands() -> None:
    result = runner.invoke(cli_app, ["polyfactory", "--help"])
    assert result.exit_code == 0
    assert "migrate" in result.stdout
