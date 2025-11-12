"""Persistence handler protocols and built-in implementations."""

from __future__ import annotations

import asyncio
import sqlite3
import ssl
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic_fixturegen.logging import get_logger

from .models import PersistenceContext, PersistenceRecord, dumps_payload


class SyncPersistenceHandler(Protocol):
    """Protocol implemented by synchronous persistence handlers."""

    def open(self, context: PersistenceContext) -> None:  # pragma: no cover - protocol
        ...

    def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:  # pragma: no cover - protocol
        ...

    def close(self) -> None:  # pragma: no cover - protocol
        ...


class AsyncPersistenceHandler(Protocol):
    """Protocol implemented by asynchronous persistence handlers."""

    async def open(self, context: PersistenceContext) -> None:  # pragma: no cover - protocol
        ...

    async def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:  # pragma: no cover - protocol
        ...

    async def close(self) -> None:  # pragma: no cover - protocol
        ...


class HttpPostPersistenceHandler:
    """Send each batch as a JSON payload via HTTP POST/PUT."""

    def __init__(
        self,
        *,
        url: str,
        method: str = "POST",
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
        envelope: str | None = None,
        verify_ssl: bool = True,
    ) -> None:
        if not url:
            raise ValueError("HTTP persistence handler requires a URL.")
        self.url = url
        self.method = method.upper() or "POST"
        self.headers = {k: v for k, v in (headers or {}).items()}
        self.timeout = timeout
        self.envelope = envelope
        self.verify_ssl = verify_ssl

    def open(self, context: PersistenceContext) -> None:  # pragma: no cover - nothing to do
        self._context = context

    def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        payload: Any = [record.payload for record in batch]
        if self.envelope:
            payload = {self.envelope: payload}
        data = dumps_payload(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        request = Request(self.url, data=data, method=self.method, headers=headers)
        context = None
        if not self.verify_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        logger = get_logger()
        logger.debug(
            "Sending persistence batch",
            event="persistence_http_batch",
            url=self.url,
            method=self.method,
            size=len(batch),
        )
        try:
            with urlopen(request, timeout=self.timeout, context=context) as response:
                status = getattr(response, "status", None) or response.getcode()
                if status >= 400:
                    raise RuntimeError(f"HTTP {status} returned by persistence endpoint")
        except HTTPError as exc:  # pragma: no cover - exercised via RuntimeError
            raise RuntimeError(f"HTTP {exc.code} returned by persistence endpoint") from exc
        except URLError as exc:  # pragma: no cover - network dependent
            raise RuntimeError(f"Failed to reach persistence endpoint: {exc.reason}") from exc

    def close(self) -> None:  # pragma: no cover - nothing to do
        return None


class AsyncHttpPostPersistenceHandler:
    """Async wrapper around the synchronous HTTP handler."""

    def __init__(self, **kwargs: Any) -> None:
        self._delegate = HttpPostPersistenceHandler(**kwargs)

    async def open(self, context: PersistenceContext) -> None:
        self._delegate.open(context)

    async def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._delegate.persist_batch, batch)

    async def close(self) -> None:
        return None


class SQLiteJSONPersistenceHandler:
    """Store batches as JSON payloads inside a SQLite table."""

    def __init__(
        self,
        *,
        database: str,
        table: str = "pfg_records",
        ensure_table: bool = True,
        journal_mode: str | None = "WAL",
    ) -> None:
        if not database:
            raise ValueError("SQLite persistence handler requires a database path.")
        self.database = Path(database)
        self.table = table
        self.ensure_table = ensure_table
        if journal_mode and not journal_mode.isalpha():
            raise ValueError("journal_mode must contain alphabetic characters only.")
        self.journal_mode = journal_mode
        self._connection: sqlite3.Connection | None = None

        if not _is_safe_identifier(self.table):
            raise ValueError("SQLite table names must consist of letters, numbers, or underscores.")

    def open(self, context: PersistenceContext) -> None:
        self._connection = sqlite3.connect(self.database)
        if self.journal_mode:
            self._connection.execute(f"PRAGMA journal_mode={self.journal_mode}")
        if self.ensure_table:
            self._connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "model TEXT NOT NULL,"
                "payload TEXT NOT NULL"
                ")"
            )
        self._connection.commit()

    def persist_batch(self, batch: Sequence[PersistenceRecord]) -> None:
        if not batch:
            return
        if self._connection is None:
            raise RuntimeError("SQLite handler is not open.")
        rows = [(record.model, record.to_json()) for record in batch]
        self._connection.executemany(
            f"INSERT INTO {self.table} (model, payload) VALUES (?, ?)",
            rows,
        )
        self._connection.commit()

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.commit()
        self._connection.close()
        self._connection = None


def _is_safe_identifier(value: str) -> bool:
    if not value:
        return False
    return value.replace("_", "").isalnum()


__all__ = [
    "AsyncPersistenceHandler",
    "AsyncHttpPostPersistenceHandler",
    "HttpPostPersistenceHandler",
    "SQLiteJSONPersistenceHandler",
    "SyncPersistenceHandler",
]
