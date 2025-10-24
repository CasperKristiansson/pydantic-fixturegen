"""Utilities for loading and interacting with fixturegen plugins."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from importlib import metadata
from typing import Any

import pluggy
from pydantic_fixturegen.plugins import hookspecs

_plugin_manager = pluggy.PluginManager("pfg")
_plugin_manager.add_hookspecs(hookspecs)
_loaded_groups: set[str] = set()


def get_plugin_manager() -> pluggy.PluginManager:
    """Return the global plugin manager."""

    return _plugin_manager


def register_plugin(plugin: Any) -> None:
    """Register a plugin object with the global manager."""

    with suppress(ValueError):  # already registered
        _plugin_manager.register(plugin)


def load_entrypoint_plugins(
    group: str = "pydantic_fixturegen",
    *,
    force: bool = False,
) -> list[Any]:
    """Load plugins declared via entry points."""

    if group in _loaded_groups and not force:
        return []

    if force:
        _loaded_groups.discard(group)

    entry_points = metadata.entry_points()
    selector = getattr(entry_points, "select", None)
    if selector is not None:
        entries: Iterable[Any] = selector(group=group)
    else:  # pragma: no cover - Python <3.10 fallback
        entries = entry_points.get(group, [])

    plugins: list[Any] = []
    for entry in entries:
        plugin = entry.load()
        register_plugin(plugin)
        plugins.append(plugin)

    _loaded_groups.add(group)
    return plugins


def emit_artifact(kind: str, context: hookspecs.EmitterContext) -> bool:
    """Invoke emitter plugins for the given artifact.

    Returns ``True`` when a plugin handled the emission. When ``True`` is
    returned, the caller should skip the default emission behaviour.
    """

    results = _plugin_manager.hook.pfg_emit_artifact(kind=kind, context=context)
    return any(bool(result) for result in results)


__all__ = ["emit_artifact", "get_plugin_manager", "load_entrypoint_plugins", "register_plugin"]
