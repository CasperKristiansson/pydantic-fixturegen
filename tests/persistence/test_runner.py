from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.persistence.runner import PersistenceRunner
from tests.persistence_helpers import FlakyHandler, SyncCaptureHandler


class SampleModel(BaseModel):
    value: int


def _snapshot() -> ConfigSnapshot:
    return ConfigSnapshot(
        seed=None,
        include=(),
        exclude=(),
        time_anchor=None,
    )


def _factory() -> dict[str, Any]:
    return {"value": 1}


def test_persistence_runner_sync_batches() -> None:
    handler = SyncCaptureHandler()
    runner = PersistenceRunner(
        handler=handler,
        handler_kind="sync",
        handler_name="capture",
        sample_factory=_factory,
        model_cls=SampleModel,
        related_models=(),
        count=3,
        batch_size=2,
        max_retries=1,
        retry_wait=0.0,
        logger=get_logger(),
        warnings=(),
        config_snapshot=_snapshot(),
        options={},
    )

    stats = runner.run()

    assert stats.records == 3
    assert stats.batches == 2
    assert stats.retries == 0


def test_persistence_runner_retries() -> None:
    handler = FlakyHandler(fail_times=1)
    runner = PersistenceRunner(
        handler=handler,
        handler_kind="sync",
        handler_name="flaky",
        sample_factory=_factory,
        model_cls=SampleModel,
        related_models=(),
        count=2,
        batch_size=2,
        max_retries=2,
        retry_wait=0.0,
        logger=get_logger(),
        warnings=(),
        config_snapshot=_snapshot(),
        options={},
    )

    stats = runner.run()

    assert stats.records == 2
    assert stats.retries == 1
