from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.diff import DiffReport
from tests._cli import create_cli_runner

runner = create_cli_runner()


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


def test_diff_json_reports_extra_file(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_dir = tmp_path / "artifacts"
    json_dir.mkdir()
    json_out = json_dir / "products.json"

    runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(json_out),
            "--n",
            "2",
            "--seed",
            "7",
            "--shard-size",
            "1",
        ],
    )

    extra = json_dir / "products-999.json"
    extra.write_text("[]", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "2",
            "--json-shard-size",
            "1",
            "--seed",
            "7",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "Unexpected extra JSON artifact" in diff_result.stdout


def test_diff_schema_detects_drift(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    schema_out = tmp_path / "schema" / "product.json"

    runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(schema_out),
        ],
    )

    schema_out.write_text("{}", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--schema-out",
            str(schema_out),
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "Schema artifact differs" in diff_result.stdout


def test_diff_handles_internal_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "missing.json"

    def raise_discovery(**_: object) -> list[DiffReport]:
        raise DiscoveryError("broken")

    monkeypatch.setattr("pydantic_fixturegen.cli.diff._execute_diff", raise_discovery)

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-errors",
            str(module_path),
        ],
    )

    assert result.exit_code == 10
    assert "broken" in result.stdout


def test_diff_json_errors_payload_on_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "existing.json"
    json_out.write_text("[]", encoding="utf-8")

    report = DiffReport(
        kind="json",
        target=json_out,
        checked_paths=[json_out],
        messages=["diff"],
        diff_outputs=[(str(json_out), "---")],
        summary=None,
        constraint_report={"fields": 1},
        time_anchor="2024-01-01T00:00:00+00:00",
    )

    monkeypatch.setattr("pydantic_fixturegen.cli.diff._execute_diff", lambda **_: [report])

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-errors",
            "--json-out",
            str(json_out),
            str(module_path),
        ],
    )

    assert result.exit_code == 50
    assert '"kind": "json"' in result.stdout


def test_diff_fixtures_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    fixtures_out = tmp_path / "fixtures" / "test_products.py"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(fixtures_out),
            "--seed",
            "123",
        ],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--fixtures-out",
            str(fixtures_out),
            "--seed",
            "123",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "Fixtures artifact matches" in diff_result.stdout


def test_diff_schema_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    schema_out = tmp_path / "schema" / "product.json"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(schema_out),
        ],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--schema-out",
            str(schema_out),
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "Schema artifact matches" in diff_result.stdout
