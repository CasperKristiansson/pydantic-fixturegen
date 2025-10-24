from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pydantic_fixturegen.cli import app as cli_app

runner = CliRunner()


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Address(BaseModel):
    city: str
    zip_code: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class Product(BaseModel):
    sku: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_schema_single_model(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "user_schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["title"] == "User"
    assert "properties" in payload


def test_gen_schema_combined_models(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "bundle.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"Address", "Product", "User"}


def test_gen_schema_indent_override(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "compact.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.Address",
            "--indent",
            "0",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert "\n" not in text
