from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic_fixturegen.persistence.models import PersistenceContext, PersistenceRecord


class SyncCaptureHandler:
    emitted: list[list[dict[str, Any]]] = []

    def __init__(self, *, marker: str | None = None) -> None:
        self.marker = marker

    def open(self, context: PersistenceContext) -> None:
        type(self).emitted.clear()

    def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        type(self).emitted.append([dict(record.payload) for record in batch])

    def close(self) -> None:  # pragma: no cover - nothing to do
        return None


class AsyncCaptureHandler:
    emitted: list[int] = []

    async def open(self, context: PersistenceContext) -> None:
        type(self).emitted.clear()

    async def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        type(self).emitted.append(len(batch))

    async def close(self) -> None:  # pragma: no cover - nothing to do
        return None


class FlakyHandler(SyncCaptureHandler):
    def __init__(self, *, fail_times: int = 1) -> None:
        super().__init__()
        self._remaining = fail_times

    def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("Transient failure")
        super().persist_batch(batch)
