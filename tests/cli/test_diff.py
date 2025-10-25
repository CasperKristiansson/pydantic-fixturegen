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


class Product(BaseModel):
    name: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_diff_json_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "products.json"

    gen_result = runner.invoke(
        cli_app,
        ["gen", "json", str(module_path), "--out", str(json_out), "--n", "2", "--seed", "123"],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "2",
            "--seed",
            "123",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "JSON artifacts match" in diff_result.stdout


def test_diff_json_detects_changes(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "products.json"

    runner.invoke(
        cli_app,
        ["gen", "json", str(module_path), "--out", str(json_out), "--n", "1", "--seed", "42"],
    )

    json_out.write_text("[]\n", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "1",
            "--seed",
            "42",
            "--show-diff",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "JSON differences detected" in diff_result.stdout
    assert "@@" in diff_result.stdout  # unified diff marker


def test_diff_json_errors_payload(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing_json = tmp_path / "artifacts" / "missing.json"

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-errors",
            "--json-out",
            str(missing_json),
            str(module_path),
        ],
    )

    assert result.exit_code == 50
    assert "DiffError" in result.stdout
    assert "Missing JSON artifact" in result.stdout


def test_diff_fixtures_missing_file(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    fixtures_out = tmp_path / "fixtures" / "test_products.py"

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--fixtures-out",
            str(fixtures_out),
            str(module_path),
        ],
    )

    assert result.exit_code == 1
    assert "Missing fixtures module" in result.stdout
