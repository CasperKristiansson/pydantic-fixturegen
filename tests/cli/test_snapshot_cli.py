from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.api import generate_json
from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_snapshot_verify_detects_drift(tmp_path: Path) -> None:
    module = _write_module(tmp_path)
    snapshot_path = tmp_path / "snapshots" / "users.json"
    generate_json(
        module,
        out=snapshot_path,
        include=["models.User"],
        count=1,
        indent=2,
        seed=42,
    )
    snapshot_path.write_text("[]", encoding="utf-8")

    result = runner.invoke(
        cli_app,
        [
            "snapshot",
            "verify",
            str(module),
            "--json-out",
            str(snapshot_path),
            "--include",
            "models.User",
            "--json-count",
            "1",
            "--json-indent",
            "2",
            "--seed",
            "42",
        ],
    )

    assert result.exit_code == 1
    assert "JSON artifact differs" in result.stdout


def test_snapshot_write_refreshes_artifact(tmp_path: Path) -> None:
    module = _write_module(tmp_path)
    snapshot_path = tmp_path / "snapshots" / "users.json"
    generate_json(
        module,
        out=snapshot_path,
        include=["models.User"],
        count=1,
        indent=2,
        seed=42,
    )
    snapshot_path.write_text("[]", encoding="utf-8")

    result = runner.invoke(
        cli_app,
        [
            "snapshot",
            "write",
            str(module),
            "--json-out",
            str(snapshot_path),
            "--include",
            "models.User",
            "--json-count",
            "1",
            "--json-indent",
            "2",
            "--seed",
            "42",
        ],
    )

    assert result.exit_code == 0
    data = snapshot_path.read_text(encoding="utf-8")
    assert data != "[]"
    assert "Snapshots refreshed." in result.stdout


def test_snapshot_cli_requires_artifact(tmp_path: Path) -> None:
    module = _write_module(tmp_path)
    result = runner.invoke(cli_app, ["snapshot", "verify", str(module)])
    assert result.exit_code != 0
    assert "Provide at least one" in (result.stdout + result.stderr)
