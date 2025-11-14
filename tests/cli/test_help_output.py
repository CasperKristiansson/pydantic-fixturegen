from __future__ import annotations

import re

from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.core.version import get_tool_version
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


def test_root_version_option() -> None:
    result = runner.invoke(cli_app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"pydantic-fixturegen {get_tool_version()}"
