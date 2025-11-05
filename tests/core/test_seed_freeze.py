from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.core.seed_freeze import (
    FREEZE_FILE_VERSION,
    FreezeStatus,
    SeedFreezeFile,
)


def test_seed_freeze_roundtrip(tmp_path: Path) -> None:
    freeze_path = tmp_path / ".pfg-seeds.json"
    manager = SeedFreezeFile.load(freeze_path)
    assert manager.records == {}

    manager.record_seed("pkg.Model", 123, model_digest="abc")
    manager.save()

    data = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert data["version"] == FREEZE_FILE_VERSION
    assert data["models"]["pkg.Model"]["seed"] == 123
    assert data["models"]["pkg.Model"]["model_digest"] == "abc"


def test_seed_freeze_stale_detection(tmp_path: Path) -> None:
    freeze_path = tmp_path / ".pfg-seeds.json"
    freeze_path.write_text(
        json.dumps(
            {
                "version": FREEZE_FILE_VERSION,
                "models": {"pkg.Model": {"seed": 5, "model_digest": "digest-a"}},
            }
        ),
        encoding="utf-8",
    )

    manager = SeedFreezeFile.load(freeze_path)
    seed, status = manager.resolve_seed("pkg.Model", model_digest="digest-b")

    assert seed == 5
    assert status is FreezeStatus.STALE


def test_seed_freeze_invalid_json_records_message(tmp_path: Path) -> None:
    freeze_path = tmp_path / ".pfg-seeds.json"
    freeze_path.write_text("{ not-json }", encoding="utf-8")

    manager = SeedFreezeFile.load(freeze_path)
    assert manager.messages
    assert manager.records == {}
