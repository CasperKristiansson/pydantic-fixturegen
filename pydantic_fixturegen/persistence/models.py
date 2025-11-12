"""Dataclasses shared by persistence handlers and runners."""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from pydantic_fixturegen.logging import Logger
from pydantic_fixturegen.api.models import ConfigSnapshot

HandlerKind = Literal["sync", "async"]


def _json_default(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "hex") and callable(value.hex):  # uuid.UUID, secrets.token
        try:
            return value.hex
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)


def dumps_payload(payload: Any) -> str:
    """Serialise payloads for handlers that require JSON bodies."""

    return json.dumps(payload, default=_json_default, ensure_ascii=False)


@dataclass(slots=True)
class PersistenceRecord:
    """A single record destined for a persistence handler."""

    model: str
    payload: Mapping[str, Any]
    case_index: int

    def to_json(self) -> str:
        return dumps_payload(self.payload)


@dataclass(slots=True)
class PersistenceContext:
    """Context describing the active persistence session."""

    model: type[Any]
    related_models: Sequence[type[Any]]
    total_records: int
    batch_size: int
    handler_name: str
    options: Mapping[str, Any]
    run_id: str
    warnings: Sequence[str]
    logger: Logger
    config: ConfigSnapshot
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PersistenceStats:
    """Execution metrics reported after a persistence run."""

    handler_name: str
    batches: int = 0
    records: int = 0
    retries: int = 0
    duration: float = 0.0

    def record_batch(self, size: int) -> None:
        self.batches += 1
        self.records += size

    def record_retry(self) -> None:
        self.retries += 1
