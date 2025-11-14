from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.persistence import handlers as handlers_mod
from pydantic_fixturegen.persistence.models import (
    PersistenceContext,
    PersistenceRecord,
)


def _context(tmp_path) -> PersistenceContext:
    return PersistenceContext(
        model=dict,
        related_models=(),
        total_records=1,
        batch_size=1,
        handler_name="handler",
        options={},
        run_id="run",
        warnings=(),
        logger=get_logger(),
        config=ConfigSnapshot(
            seed=None,
            include=(),
            exclude=(),
            time_anchor=None,
        ),
        metadata={},
    )


def _record() -> PersistenceRecord:
    return PersistenceRecord(model="Widget", payload={"value": 1}, case_index=1)


def test_http_post_handler_envelope(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    context = _context(tmp_path)
    captured: dict[str, Any] = {}

    class DummyResponse:
        def __init__(self, status: int = 200) -> None:
            self.status = status

        def getcode(self) -> int:
            return self.status

        def __enter__(self) -> DummyResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, ANN202
            return None

    def fake_urlopen(request: Any, timeout: float, context: Any) -> DummyResponse:
        captured["data"] = request.data
        captured["headers"] = dict(request.header_items())
        captured["context"] = context
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(handlers_mod, "urlopen", fake_urlopen)

    handler = handlers_mod.HttpPostPersistenceHandler(
        url="https://example.invalid",
        method="post",
        timeout=5,
        envelope="items",
        verify_ssl=False,
    )

    handler.open(context)
    handler.persist_batch([_record()])
    handler.close()

    assert b'"items": [' in captured["data"]
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["timeout"] == 5
    assert captured["context"] is not None


def test_http_post_handler_errors_on_bad_status(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    context = _context(tmp_path)

    class ErrorResponse:
        def getcode(self) -> int:
            return 500

        def __enter__(self) -> ErrorResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, ANN202
            return None

    monkeypatch.setattr(handlers_mod, "urlopen", lambda *args, **kwargs: ErrorResponse())

    handler = handlers_mod.HttpPostPersistenceHandler(url="https://example.invalid")
    handler.open(context)

    with pytest.raises(RuntimeError):
        handler.persist_batch([_record()])


def test_async_http_post_handler_executes_delegate(tmp_path) -> None:
    context = _context(tmp_path)
    calls: list[Any] = []

    handler = handlers_mod.AsyncHttpPostPersistenceHandler(url="https://example.invalid")
    handler._delegate = SimpleNamespace(  # type: ignore[attr-defined]
        open=lambda ctx: calls.append(("open", ctx.handler_name)),
        persist_batch=lambda batch: calls.append(("persist", len(batch))),
        close=lambda: calls.append(("close", None)),
    )

    async def _run() -> None:
        await handler.open(context)
        await handler.persist_batch([_record(), _record()])
        await handler.close()

    asyncio.run(_run())

    assert calls[0][0] == "open"
    assert calls[1] == ("persist", 2)


def test_sqlite_handler_persists_batches(tmp_path) -> None:
    database = tmp_path / "persistence.db"
    handler = handlers_mod.SQLiteJSONPersistenceHandler(database=str(database), table="events")
    context = _context(tmp_path)
    handler.open(context)
    handler.persist_batch([_record(), _record()])
    handler.close()

    import sqlite3

    conn = sqlite3.connect(database)
    try:
        rows = list(conn.execute("SELECT COUNT(*) FROM events"))
    finally:
        conn.close()
    assert rows[0][0] == 2


def test_sqlite_handler_requires_open(tmp_path) -> None:
    handler = handlers_mod.SQLiteJSONPersistenceHandler(database=str(tmp_path / "db.db"))
    with pytest.raises(RuntimeError):
        handler.persist_batch([_record()])


def test_identifier_validator() -> None:
    assert handlers_mod._is_safe_identifier("valid_name")
    assert not handlers_mod._is_safe_identifier("")
    assert not handlers_mod._is_safe_identifier("invalid-name")
