from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def test_schema_config_stdout() -> None:
    result = runner.invoke(cli_app, ["schema", "config", "--compact"])

    assert result.exit_code == 0
    assert "\"$schema\"" in result.stdout
    assert "pydantic-fixturegen configuration" in result.stdout


def test_schema_config_write(tmp_path: Path) -> None:
    target = tmp_path / "config.schema.json"

    result = runner.invoke(cli_app, ["schema", "config", "--out", str(target)])

    assert result.exit_code == 0
    assert target.is_file()
    contents = target.read_text(encoding="utf-8")
    assert "https://json-schema.org/draft/2020-12/schema" in contents
