from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_models(tmp_path: Path) -> Path:
    module = tmp_path / "models.py"
    module.write_text(
        """
from typing import Literal

from pydantic import BaseModel


class Profile(BaseModel):
    username: str
    active: bool


class User(BaseModel):
    name: str
    age: int
    profile: Profile
    role: Literal["admin", "user"]
""",
        encoding="utf-8",
    )
    return module


def test_explain_outputs_summary(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "explain",
            str(module),
        ],
    )

    assert result.exit_code == 0
    assert "models.User" in result.stdout
    assert "profile" in result.stdout
    assert "role" in result.stdout


def test_explain_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        ["gen", "explain", "--json-errors", str(missing)],
    )

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout
