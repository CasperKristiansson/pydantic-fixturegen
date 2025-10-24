from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str


class User(BaseModel):
    name: str
    age: int
    address: Address
""",
        encoding="utf-8",
    )
    return module_path


def test_doctor_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "Coverage: 3/3 fields" in result.stdout
    assert "Issues: none" in result.stdout


def test_doctor_reports_provider_issue(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Note(BaseModel):
    payload: object
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "type 'any'" in result.stdout.lower()


def test_doctor_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        ["doctor", "--json-errors", str(missing)],
    )

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout
