from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import BaseModel
from pydantic_fixturegen.api import models


class DummyModel(BaseModel):
    foo: int


def test_config_snapshot_roundtrip() -> None:
    now = dt.datetime(2024, 7, 4, 12, 30, tzinfo=dt.timezone.utc)
    snapshot = models.ConfigSnapshot(
        seed=42,
        include=("pkg.ModelA",),
        exclude=("pkg.ModelB",),
        time_anchor=now,
    )

    assert snapshot.seed == 42
    assert snapshot.include == ("pkg.ModelA",)
    assert snapshot.exclude == ("pkg.ModelB",)
    assert snapshot.time_anchor is now


def test_json_generation_result_payload() -> None:
    base_output = Path("/tmp/out")
    result = models.JsonGenerationResult(
        paths=(base_output / "data.json",),
        base_output=base_output,
        model=DummyModel,
        config=models.ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        constraint_summary={"fields": 1},
        warnings=("warn",),
        delegated=False,
    )

    assert result.paths[0].name == "data.json"
    assert result.model is DummyModel
    assert result.config.include == ()
    assert result.delegated is False


def test_fixtures_generation_result_payload() -> None:
    base_output = Path("/tmp/out")
    result = models.FixturesGenerationResult(
        path=base_output / "conftest.py",
        base_output=base_output,
        models=(DummyModel,),
        config=models.ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        metadata={"style": "functions"},
        warnings=(),
        constraint_summary=None,
        skipped=False,
        delegated=True,
        style="functions",
        scope="function",
        return_type="DummyModel",
        cases=3,
    )

    assert result.path.name == "conftest.py"
    assert result.models == (DummyModel,)
    assert result.delegated is True
    assert result.cases == 3


def test_schema_generation_result_payload() -> None:
    base_output = Path("/tmp/out")
    result = models.SchemaGenerationResult(
        path=None,
        base_output=base_output,
        models=(DummyModel,),
        config=models.ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        warnings=("w1", "w2"),
        delegated=False,
    )

    assert result.path is None
    assert result.warnings == ("w1", "w2")
    assert result.delegated is False
