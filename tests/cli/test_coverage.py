from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

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


def test_coverage_report_json_unused_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_coverage_report_fail_on_heuristics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_models(tmp_path)
    monkeypatch.setattr(coverage_mod, "load_config", lambda **_: AppConfig())

    result = runner.invoke(
        cli_app,
        ["coverage", str(module_path), "--fail-on", "heuristics"],
    )

    assert result.exit_code == 2
