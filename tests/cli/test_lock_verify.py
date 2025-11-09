from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Entry(BaseModel):
    id: int
    email: str
""",
        encoding="utf-8",
    )
    return module_path


def test_pfg_lock_and_verify(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "lock",
            "--lockfile",
            str(lockfile),
            str(module_path),
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic aid
        print(result.stdout)
    assert result.exit_code == 0
    assert lockfile.exists()

    verify_result = runner.invoke(
        cli_app,
        [
            "verify",
            "--lockfile",
            str(lockfile),
            str(module_path),
        ],
    )
    assert verify_result.exit_code == 0


def test_pfg_verify_detects_drift(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()

    runner.invoke(
        cli_app,
        [
            "lock",
            "--lockfile",
            str(lockfile),
            str(module_path),
        ],
    )

    data = json.loads(lockfile.read_text(encoding="utf-8"))
    data["models"][0]["coverage"]["covered"] = 0
    lockfile.write_text(json.dumps(data, indent=2), encoding="utf-8")

    verify_result = runner.invoke(
        cli_app,
        [
            "verify",
            "--lockfile",
            str(lockfile),
            str(module_path),
        ],
    )
    assert verify_result.exit_code != 0


def test_pfg_lock_reports_up_to_date(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()
    runner.invoke(
        cli_app,
        ["lock", "--lockfile", str(lockfile), str(module_path)],
    )
    second = runner.invoke(
        cli_app,
        ["lock", "--lockfile", str(lockfile), str(module_path)],
    )
    assert "already up to date" in second.stdout


def test_pfg_verify_missing_lockfile(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()
    missing = tmp_path / "missing-lock.json"
    result = runner.invoke(
        cli_app,
        ["verify", "--lockfile", str(missing), str(module_path)],
    )
    assert result.exit_code != 0


def test_pfg_lock_requires_target(tmp_path: Path) -> None:
    lockfile = tmp_path / ".pfg-lock.json"
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        ["lock", "--lockfile", str(lockfile)],
    )
    assert result.exit_code != 0


def test_pfg_verify_requires_target(tmp_path: Path) -> None:
    lockfile = tmp_path / ".pfg-lock.json"
    lockfile.write_text("{}", encoding="utf-8")
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        ["verify", "--lockfile", str(lockfile)],
    )
    assert result.exit_code != 0
