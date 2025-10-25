from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Item(BaseModel):
    name: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_check_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    result = runner.invoke(cli_app, ["check", str(module_path)])

    assert result.exit_code == 0
    assert "Configuration OK" in result.stdout
    assert "Discovered 1 model" in result.stdout
    assert "Check complete" in result.stdout


def test_check_emitter_path_validation(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing_parent = tmp_path / "does" / "not" / "exist.json"

    result = runner.invoke(
        cli_app,
        [
            "check",
            "--json-out",
            str(missing_parent),
            str(module_path),
        ],
    )

    assert result.exit_code == 10
    assert "does not exist" in result.stderr


def test_check_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(cli_app, ["check", "--json-errors", str(missing)])

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout
    assert "missing.py" in result.stdout
