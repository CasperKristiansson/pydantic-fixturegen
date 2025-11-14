from __future__ import annotations

import re

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def test_persist_help_lists_options() -> None:
    result = runner.invoke(cli_app, ["persist", "--help"])
    assert result.exit_code == 0
    stdout = _strip_ansi(result.stdout)
    assert "--handler" in stdout
    assert "--batch-size" in stdout


def test_polyfactory_help_lists_subcommands() -> None:
    result = runner.invoke(cli_app, ["polyfactory", "--help"])
    assert result.exit_code == 0
    stdout = _strip_ansi(result.stdout)
    assert "migrate" in stdout
