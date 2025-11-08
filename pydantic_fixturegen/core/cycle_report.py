"""Utilities for tracking cycle-handling metadata per generated instance."""

from __future__ import annotations

import weakref
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CycleEvent:
    """Describes how a recursive field was resolved."""

    path: str
    policy: str
    reason: str  # e.g. "cycle" or "max_depth"
    ref_path: str | None = None
    fallback: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "policy": self.policy,
            "reason": self.reason,
        }
        if self.ref_path:
            payload["ref"] = self.ref_path
        if self.fallback:
            payload["fallback"] = self.fallback
        return payload


_cycle_registry: dict[int, tuple[CycleEvent, ...]] = {}
_cycle_finalizers: dict[int, weakref.finalize[Any, Any]] = {}


def _purge_cycle_entry(key: int) -> None:
    _cycle_registry.pop(key, None)
    _cycle_finalizers.pop(key, None)


def attach_cycle_events(instance: Any, events: Iterable[CycleEvent]) -> None:
    """Associate a sequence of cycle events with ``instance``."""

    events_tuple = tuple(events)
    if not events_tuple:
        return

    key = id(instance)
    try:
        finalizer = weakref.finalize(instance, _purge_cycle_entry, key)
    except TypeError:
        # Instance is not weak-referenceable; ignore cycle metadata.
        return
    previous = _cycle_finalizers.pop(key, None)
    if previous is not None:
        previous.detach()
    _cycle_registry[key] = events_tuple
    _cycle_finalizers[key] = finalizer


def consume_cycle_events(instance: Any) -> tuple[CycleEvent, ...]:
    """Return and clear cycle metadata for ``instance`` if present."""

    key = id(instance)
    payload = _cycle_registry.pop(key, ())
    finalizer = _cycle_finalizers.pop(key, None)
    if finalizer is not None:
        finalizer.detach()
    return payload


__all__ = ["CycleEvent", "attach_cycle_events", "consume_cycle_events"]
