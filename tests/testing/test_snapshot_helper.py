from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.api import generate_json
from pydantic_fixturegen.testing import JsonSnapshotConfig, SnapshotRunner
from pydantic_fixturegen.testing.snapshot import SnapshotUpdateMode
from pytest import MonkeyPatch

pytest_plugins = ["pydantic_fixturegen.testing.pytest_plugin"]


def _write_module(root: Path, content: str) -> Path:
    module_path = root / "models.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


def _model_source(extra_field: str = "") -> str:
    body = "    id: int\n    name: str\n"
    if extra_field:
        body += f"    {extra_field}\n"
    return f"from pydantic import BaseModel\n\n\nclass User(BaseModel):\n{body}"


def _read_json(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_snapshot_helper_passes_when_artifacts_match(
    tmp_path: Path,
    pfg_snapshot: SnapshotRunner,
) -> None:
    module_path = _write_module(tmp_path, _model_source())
    snapshot_path = tmp_path / "snapshots" / "users.json"
    generate_json(
        module_path,
        out=snapshot_path,
        include=["models.User"],
        count=1,
        indent=2,
        seed=42,
    )

    config = JsonSnapshotConfig(out=snapshot_path, indent=2)
    pfg_snapshot.assert_artifacts(
        target=module_path,
        json=config,
        include=["models.User"],
        seed=42,
    )


def test_snapshot_helper_raises_when_different(
    tmp_path: Path,
    pfg_snapshot: SnapshotRunner,
) -> None:
    module_path = _write_module(tmp_path, _model_source())
    snapshot_path = tmp_path / "snapshots" / "users.json"
    generate_json(
        module_path,
        out=snapshot_path,
        include=["models.User"],
        count=1,
        indent=2,
        seed=42,
    )

    # Corrupt snapshot
    snapshot_path.write_text("[]", encoding="utf-8")

    config = JsonSnapshotConfig(out=snapshot_path, indent=2)
    with pytest.raises(AssertionError) as exc:
        pfg_snapshot.assert_artifacts(
            target=module_path,
            json=config,
            include=["models.User"],
            seed=42,
        )

    assert "mismatch" in str(exc.value)


def test_snapshot_helper_updates_when_enabled(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path, _model_source("email: str | None = None"))
    snapshot_path = tmp_path / "snapshots" / "users.json"
    generate_json(
        module_path,
        out=snapshot_path,
        include=["models.User"],
        count=1,
        indent=2,
        seed=42,
    )
    original = snapshot_path.read_text(encoding="utf-8")

    # Modify model to introduce drift
    module_path = _write_module(tmp_path, _model_source("active: bool = False"))
    snapshot_path.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("PFG_SNAPSHOT_UPDATE", "update")
    runner = SnapshotRunner(update_mode=SnapshotUpdateMode.from_env())

    config = JsonSnapshotConfig(out=snapshot_path, indent=2)
    runner.assert_artifacts(
        target=module_path,
        json=config,
        include=["models.User"],
        seed=42,
    )

    updated = snapshot_path.read_text(encoding="utf-8")
    assert updated != "[]"
    assert updated != original
    data = _read_json(snapshot_path)
    assert data, "Updated snapshot should contain generated payload"
