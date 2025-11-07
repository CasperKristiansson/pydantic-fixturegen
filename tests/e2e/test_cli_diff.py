from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

MODULE_SOURCE = """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
"""


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")
    return module_path


def test_diff_reports_drift_and_shows_unified_diff(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()
    fixtures_path = tmp_path / "fixtures" / "test_models.py"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(fixtures_path),
            "--include",
            "models.User",
            "--seed",
            "5",
        ],
    )
    assert gen_result.exit_code == 0, gen_result.output

    fixtures_path.write_text("corrupted output", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--fixtures-out",
            str(fixtures_path),
            "--include",
            "models.User",
            "--show-diff",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "FIXTURES differences detected" in diff_result.output
    assert "--- " in diff_result.output
