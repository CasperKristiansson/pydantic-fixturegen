from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.core.errors import PersistenceError
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.persistence.runner import PersistenceRunner
from tests.persistence_helpers import (
    AsyncCaptureHandler,
    FlakyHandler,
    SyncCaptureHandler,
)


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


def test_persistence_runner_async_batches() -> None:
    handler = AsyncCaptureHandler()
    runner = PersistenceRunner(
        handler=handler,
        handler_kind="async",
        handler_name="async-capture",
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
    assert handler.emitted == [2, 1]


def test_persistence_runner_raises_after_exhausting_retries() -> None:
    class AlwaysFailHandler(SyncCaptureHandler):
        def persist_batch(self, batch: Any) -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    handler = AlwaysFailHandler()
    runner = PersistenceRunner(
        handler=handler,
        handler_kind="sync",
        handler_name="failure",
        sample_factory=_factory,
        model_cls=SampleModel,
        related_models=(),
        count=1,
        batch_size=1,
        max_retries=0,
        retry_wait=0.0,
        logger=get_logger(),
        warnings=(),
        config_snapshot=_snapshot(),
        options={},
    )

    with pytest.raises(PersistenceError) as excinfo:
        runner.run()

    assert excinfo.value.details["attempts"] == 1
    assert excinfo.value.details["batch_size"] == 1


def test_call_sync_rejects_coroutine_return() -> None:
    async def _async_open() -> None:
        return None

    created: list[Any] = []

    def _bad_open() -> Any:
        coro = _async_open()
        created.append(coro)
        return coro

    with pytest.raises(RuntimeError):
        PersistenceRunner._call_sync(_bad_open)

    for coro in created:
        coro.close()
