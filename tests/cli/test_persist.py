from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner
from tests.persistence_helpers import SyncCaptureHandler

runner = create_cli_runner()


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
""",
        encoding="utf-8",
    )
    return module_path


def test_persist_with_dotted_handler(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    SyncCaptureHandler.emitted.clear()

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--n",
            "2",
            "--batch-size",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert SyncCaptureHandler.emitted and len(SyncCaptureHandler.emitted[0]) == 1


def test_persist_uses_configured_handler(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pydantic_fixturegen.persistence.handlers.capture]
path = "tests.persistence_helpers:SyncCaptureHandler"
""",
        encoding="utf-8",
    )
    SyncCaptureHandler.emitted.clear()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "capture",
            "--handler-config",
            "{\"marker\": \"x\"}",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert SyncCaptureHandler.emitted
