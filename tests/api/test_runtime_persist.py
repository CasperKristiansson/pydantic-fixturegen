from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.api._runtime import persist_samples
from tests.persistence_helpers import SyncCaptureHandler


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_persist_samples_records_freeze_seed(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    freeze_file = tmp_path / ".pfg-seeds.json"
    SyncCaptureHandler.emitted.clear()

    persist_samples(
        target=module_path,
        handler="tests.persistence_helpers:SyncCaptureHandler",
        handler_options=None,
        count=1,
        batch_size=1,
        max_retries=0,
        retry_wait=0.0,
        include=None,
        exclude=None,
        seed=7,
        now=None,
        preset=None,
        profile=None,
        respect_validators=None,
        validator_max_retries=None,
        field_overrides=None,
        field_hints=None,
        relations=None,
        with_related=None,
        max_depth=None,
        cycle_policy=None,
        rng_mode=None,
        collection_min_items=None,
        collection_max_items=None,
        collection_distribution=None,
        locale=None,
        locale_overrides=None,
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
    )

    assert freeze_file.exists()
    payload = json.loads(freeze_file.read_text(encoding="utf-8"))
    assert payload["models"]  # ensure at least one entry recorded


def test_persist_samples_dry_run_skips_handler(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    SyncCaptureHandler.emitted.clear()

    run = persist_samples(
        target=module_path,
        handler="tests.persistence_helpers:SyncCaptureHandler",
        handler_options=None,
        count=2,
        batch_size=1,
        max_retries=0,
        retry_wait=0.0,
        include=None,
        exclude=None,
        seed=None,
        now=None,
        preset=None,
        profile=None,
        respect_validators=None,
        validator_max_retries=None,
        field_overrides=None,
        field_hints=None,
        relations=None,
        with_related=None,
        max_depth=None,
        cycle_policy=None,
        rng_mode=None,
        collection_min_items=None,
        collection_max_items=None,
        collection_distribution=None,
        locale=None,
        locale_overrides=None,
        dry_run=True,
    )

    assert run.handler == "dry-run"
    assert run.records == 2
    assert SyncCaptureHandler.emitted == []
