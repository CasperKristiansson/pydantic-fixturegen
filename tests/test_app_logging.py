from __future__ import annotations

import io
import json

import pytest
from pydantic_fixturegen.logging import LOG_LEVELS, Logger, LoggerConfig


def test_logger_emits_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    logger = Logger(LoggerConfig(level=LOG_LEVELS["debug"], json=True))

    logger.info("json-event", event="custom_event", detail="value")

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "custom_event"
    assert payload["context"] == {"detail": "value"}
    assert payload["level"] == "info"


def test_logger_emits_colored_output(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[tuple[str, dict[str, object]]] = []

    def fake_secho(message: str, **kwargs: object) -> None:
        emitted.append((message, kwargs))

    monkeypatch.setattr("typer.secho", fake_secho)
    logger = Logger(LoggerConfig(level=LOG_LEVELS["debug"], json=False))

    logger.warn("warn-event", detail="value")

    assert emitted[0][1]["err"] is True
    context_message = emitted[1][0]
    context = json.loads(context_message)
    assert context == {"detail": "value"}


def test_logger_configure_validates_levels() -> None:
    logger = Logger()
    with pytest.raises(ValueError):
        logger.configure(level="invalid")


def test_logger_emit_rejects_unknown_levels() -> None:
    logger = Logger()
    with pytest.raises(ValueError):
        logger._emit("missing", "event")
