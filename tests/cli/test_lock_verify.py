from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Item(BaseModel):
    id: int
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_lock_accepts_options_after_path(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "lock",
            str(module_path),
            "--lockfile",
            str(lockfile),
        ],
    )

    assert result.exit_code == 0, result.output
    assert lockfile.exists()


def test_verify_accepts_options_after_path(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()

    # Create lockfile via CLI (options before path to avoid depending on order).
    result = runner.invoke(
        cli_app,
        [
            "lock",
            "--lockfile",
            str(lockfile),
            str(module_path),
        ],
    )
    assert result.exit_code == 0, result.output

    verify_result = runner.invoke(
        cli_app,
        [
            "verify",
            str(module_path),
            "--lockfile",
            str(lockfile),
        ],
    )

    assert verify_result.exit_code == 0, verify_result.output
