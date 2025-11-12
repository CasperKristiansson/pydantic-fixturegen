"""Execution helpers for persistence runs."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections.abc import Callable, Mapping, Sequence, Iterator
from typing import Any

from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.core.errors import PersistenceError
from pydantic_fixturegen.logging import Logger

from .handlers import AsyncPersistenceHandler, SyncPersistenceHandler
from .models import HandlerKind, PersistenceContext, PersistenceRecord, PersistenceStats


class PersistenceRunner:
    """Stream generated payloads into a persistence handler."""

    def __init__(
        self,
        *,
        handler: SyncPersistenceHandler | AsyncPersistenceHandler,
        handler_kind: HandlerKind,
        handler_name: str,
        sample_factory: Callable[[], Mapping[str, Any]],
        model_cls: type[Any],
        related_models: Sequence[type[Any]],
        count: int,
        batch_size: int,
        max_retries: int,
        retry_wait: float,
        logger: Logger,
        warnings: Sequence[str],
        config_snapshot: ConfigSnapshot,
        options: Mapping[str, Any],
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be >= 1")
        self.handler = handler
        self.handler_kind = handler_kind
        self.handler_name = handler_name
        self.sample_factory = sample_factory
        self.model_cls = model_cls
        self.related_models = tuple(related_models)
        self.count = count
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_wait = max(0.0, retry_wait)
        self.logger = logger
        self.warnings = tuple(warnings)
        self.config_snapshot = config_snapshot
        self.options = options
        self.run_id = uuid.uuid4().hex

    def run(self) -> PersistenceStats:
        stats = PersistenceStats(handler_name=self.handler_name)
        start = time.perf_counter()
        try:
            if self.handler_kind == "async":
                asyncio.run(self._run_async(stats))
            else:
                self._run_sync(stats)
        finally:
            stats.duration = time.perf_counter() - start
        return stats

    # ------------------------------------------------------------------ sync/async drivers
    def _run_sync(self, stats: PersistenceStats) -> None:
        context = self._build_context()
        self._call_sync(getattr(self.handler, "open", None), context)
        try:
            for batch in self._iter_batches():
                self._dispatch_batch_sync(batch, stats)
        finally:
            self._call_sync(getattr(self.handler, "close", None))

    async def _run_async(self, stats: PersistenceStats) -> None:
        context = self._build_context()
        await self._call_async(getattr(self.handler, "open", None), context)
        try:
            for batch in self._iter_batches():
                await self._dispatch_batch_async(batch, stats)
        finally:
            await self._call_async(getattr(self.handler, "close", None))

    # ------------------------------------------------------------------ dispatch helpers
    def _dispatch_batch_sync(self, batch: Sequence[PersistenceRecord], stats: PersistenceStats) -> None:
        attempt = 0
        while True:
            try:
                self.handler.persist_batch(batch)
            except Exception as exc:  # pragma: no cover - exercised via retry tests
                attempt += 1
                stats.record_retry()
                if attempt > self.max_retries:
                    raise self._failure_error(batch, attempt, exc) from exc
                time.sleep(self.retry_wait)
                continue
            stats.record_batch(len(batch))
            self.logger.info(
                "Persisted batch",
                event="persistence_batch",
                handler=self.handler_name,
                size=len(batch),
                attempt=attempt + 1,
            )
            break

    async def _dispatch_batch_async(self, batch: Sequence[PersistenceRecord], stats: PersistenceStats) -> None:
        attempt = 0
        while True:
            try:
                await self.handler.persist_batch(batch)  # type: ignore[func-returns-value]
            except Exception as exc:  # pragma: no cover - exercised via retry tests
                attempt += 1
                stats.record_retry()
                if attempt > self.max_retries:
                    raise self._failure_error(batch, attempt, exc) from exc
                await asyncio.sleep(self.retry_wait)
                continue
            stats.record_batch(len(batch))
            self.logger.info(
                "Persisted batch",
                event="persistence_batch",
                handler=self.handler_name,
                size=len(batch),
                attempt=attempt + 1,
            )
            break

    # ------------------------------------------------------------------ context helpers
    def _build_context(self) -> PersistenceContext:
        metadata = {
            "model": f"{self.model_cls.__module__}.{self.model_cls.__qualname__}",
            "related_models": [f"{model.__module__}.{model.__qualname__}" for model in self.related_models],
        }
        return PersistenceContext(
            model=self.model_cls,
            related_models=self.related_models,
            total_records=self.count,
            batch_size=self.batch_size,
            handler_name=self.handler_name,
            options=self.options,
            run_id=self.run_id,
            warnings=self.warnings,
            logger=self.logger,
            config=self.config_snapshot,
            metadata=metadata,
        )

    def _iter_batches(self) -> Iterator[Sequence[PersistenceRecord]]:
        records_remaining = self.count
        case_index = 1
        while records_remaining > 0:
            chunk = min(self.batch_size, records_remaining)
            batch: list[PersistenceRecord] = []
            for _ in range(chunk):
                payload = self.sample_factory()
                batch.append(
                    PersistenceRecord(
                        model=self.model_cls.__qualname__,
                        payload=dict(payload),
                        case_index=case_index,
                    )
                )
                case_index += 1
            records_remaining -= chunk
            yield batch

    # ------------------------------------------------------------------ util
    @staticmethod
    def _call_sync(callable_obj: Callable[..., Any] | None, *args: Any) -> None:
        if callable_obj is None:
            return
        result = callable_obj(*args)
        if inspect.isawaitable(result):  # pragma: no cover - defensive
            raise RuntimeError("Synchronous handlers cannot return awaitables.")

    @staticmethod
    async def _call_async(callable_obj: Callable[..., Any] | None, *args: Any) -> None:
        if callable_obj is None:
            return
        result = callable_obj(*args)
        if inspect.isawaitable(result):  # pragma: no cover - defensive
            await result

    def _failure_error(
        self,
        batch: Sequence[PersistenceRecord],
        attempt: int,
        exc: Exception,
    ) -> PersistenceError:
        details = {
            "handler": self.handler_name,
            "attempts": attempt,
            "batch_size": len(batch),
            "run_id": self.run_id,
        }
        return PersistenceError(
            f"Persistence handler '{self.handler_name}' failed after {attempt} attempts.",
            details=details,
        )
