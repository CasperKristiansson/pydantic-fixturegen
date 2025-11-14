from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic import BaseModel, Field
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import coverage as coverage_mod
from pydantic_fixturegen.core.config import AppConfig, RelationLinkConfig
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_models(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel


            class User(BaseModel):
                user_uuid: str
                name: str
            """
        ),
        encoding="utf-8",
    )
    return module_path


def test_coverage_report_text_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_models(tmp_path)
    monkeypatch.setattr(coverage_mod, "load_config", lambda **_: AppConfig())

    result = runner.invoke(cli_app, ["coverage", str(module_path)])

    assert result.exit_code == 0, result.stdout
    assert "Model: models.User" in result.stdout
    assert "Heuristic fields: user_uuid" in result.stdout


def test_coverage_report_json_unused_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_models(tmp_path)
    config = AppConfig(
        overrides={"models.User": {"missing": {"value": 1}}},
        relations=(RelationLinkConfig(source="models.Missing.user_id", target="models.User.id"),),
    )
    monkeypatch.setattr(coverage_mod, "load_config", lambda **_: config)

    result = runner.invoke(
        cli_app,
        [
            "coverage",
            str(module_path),
            "--format",
            "json",
            "--fail-on",
            "overrides",
        ],
    )

    assert result.exit_code == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["unused_overrides"]
    assert payload["relation_issues"]


def test_coverage_report_fail_on_heuristics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_models(tmp_path)
    monkeypatch.setattr(coverage_mod, "load_config", lambda **_: AppConfig())

    result = runner.invoke(
        cli_app,
        ["coverage", str(module_path), "--fail-on", "heuristics"],
    )

    assert result.exit_code == 2


def test_coverage_profile_option_applies_cli_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_models(tmp_path)
    captured: dict[str, Any] = {}

    def fake_load_config(*, root: Path, cli: dict[str, Any] | None = None) -> AppConfig:
        captured["cli"] = cli
        return AppConfig()

    monkeypatch.setattr(coverage_mod, "load_config", fake_load_config)

    result = runner.invoke(
        cli_app,
        ["coverage", str(module_path), "--profile", "pii-safe"],
    )

    assert result.exit_code == 0, result.stdout
    assert captured["cli"] == {"profile": "pii-safe"}


def test_coverage_out_option_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_models(tmp_path)
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(coverage_mod, "load_config", lambda **_: AppConfig())

    result = runner.invoke(
        cli_app,
        [
            "coverage",
            str(module_path),
            "--format",
            "json",
            "--out",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert result.stdout == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["models"] == 1


def test_should_fail_branches_and_errors() -> None:
    report = coverage_mod.CoverageReport(
        models=[],
        totals=coverage_mod.CoverageTotals(0, 0, 0, 0, 0, 0),
        heuristic_details=[{"field": "user_uuid"}],
        unused_overrides=[{"model_pattern": "*", "field_pattern": "name"}],
        relation_issues=[{"model": "User"}],
    )

    assert coverage_mod._should_fail(report, "heuristics") is True
    assert coverage_mod._should_fail(report, "overrides") is True
    assert coverage_mod._should_fail(report, "relations") is True
    assert coverage_mod._should_fail(report, "any") is True
    assert coverage_mod._should_fail(report, "none") is False

    with pytest.raises(typer.BadParameter):
        coverage_mod._should_fail(report, "unknown-mode")


def test_write_output_appends_newline(tmp_path: Path) -> None:
    path = tmp_path / "report.txt"

    coverage_mod._write_output(path, "payload")
    assert path.read_text(encoding="utf-8") == "payload\n"

    coverage_mod._write_output(path, "payload\n")
    assert path.read_text(encoding="utf-8") == "payload\n"


def test_coverage_override_tracker_tracks_alias_matches() -> None:
    class AliasModel(BaseModel):
        actual: int = Field(default=0, alias="alias_value")

    model_pattern = f"{AliasModel.__module__}.*AliasModel"
    override_map = {
        model_pattern: {
            "alias_value": {"ignore": True},
            "unused": {"ignore": True},
        }
    }
    override_set = coverage_mod.build_field_override_set(override_map)
    tracker = coverage_mod.CoverageOverrideTracker(override_set)
    field_info = AliasModel.model_fields["actual"]

    assert tracker.resolve(AliasModel, "actual", field_info) is True
    unused = tracker.unused()
    assert unused == [{"model_pattern": model_pattern, "field_pattern": "unused"}]


def test_model_identifier_keys_include_variants() -> None:
    class SampleModel(BaseModel):
        value: int

    keys = coverage_mod._model_identifier_keys(SampleModel)

    assert SampleModel.__name__ in keys
    assert SampleModel.__qualname__ in keys
