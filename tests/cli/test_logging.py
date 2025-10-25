from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_model(tmp_path: Path) -> Path:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    return module


def test_log_json_emits_structured_output(tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    out = tmp_path / "out.json"

    result = runner.invoke(
        cli_app,
        [
            "--log-json",
            "gen",
            "json",
            str(module),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[0])
    assert payload["level"] == "info"
    assert payload["message"] == "JSON generation complete"
    assert Path(payload["details"]["files"][0]).exists()


def test_quiet_suppresses_info_logs(tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    out = tmp_path / "out.json"

    result = runner.invoke(
        cli_app,
        [
            "--log-json",
            "--quiet",
            "gen",
            "json",
            str(module),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # First non-empty line should be the output path since info logs are suppressed
    assert lines[0] == str(out)


def test_verbose_enables_debug_logs(tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    out = tmp_path / "out.json"

    result = runner.invoke(
        cli_app,
        [
            "--log-json",
            "-v",
            "gen",
            "json",
            str(module),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    levels = [json.loads(line)["level"] for line in lines[:-1]]
    assert "debug" in levels


def test_logger_configuration_errors() -> None:
    from pydantic_fixturegen.logging import Logger

    logger = Logger()

    with pytest.raises(ValueError):
        logger.configure(level="unknown")

    logger.configure(level="debug", json_mode=True)
    logger.error("error message", reason="fail")

    logger.configure(json_mode=False)
    logger.debug("debug with extras", foo=1)
