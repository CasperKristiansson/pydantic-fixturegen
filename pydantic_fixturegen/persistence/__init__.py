"""Persistence handler interfaces and helpers."""

from __future__ import annotations

from .handlers import (
    AsyncHttpPostPersistenceHandler,
    AsyncPersistenceHandler,
    HttpPostPersistenceHandler,
    SQLiteJSONPersistenceHandler,
    SyncPersistenceHandler,
)
from .models import HandlerKind, PersistenceContext, PersistenceRecord, PersistenceStats
from .registry import PersistenceHandlerFactory, PersistenceRegistry
from .runner import PersistenceRunner

__all__ = [
    "AsyncPersistenceHandler",
    "AsyncHttpPostPersistenceHandler",
    "HandlerKind",
    "HttpPostPersistenceHandler",
    "PersistenceContext",
    "PersistenceHandlerFactory",
    "PersistenceRecord",
    "PersistenceRegistry",
    "PersistenceRunner",
    "PersistenceStats",
    "SQLiteJSONPersistenceHandler",
    "SyncPersistenceHandler",
]
