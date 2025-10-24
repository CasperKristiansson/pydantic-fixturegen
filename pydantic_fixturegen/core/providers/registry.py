"""Provider registry for mapping types to value generators."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, cast

import pluggy

from pydantic_fixturegen.plugins import hookspecs

ProviderFunc = Callable[..., Any]


@dataclass(slots=True)
class ProviderRef:
    """Descriptor for a registered provider."""

    type_id: str
    format: str | None
    name: str
    func: ProviderFunc
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ProviderRegistry:
    """Registry of provider functions addressable by type identifier and format."""

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str | None], ProviderRef] = {}
        self._plugin_manager = pluggy.PluginManager("pfg")
        self._plugin_manager.add_hookspecs(hookspecs)

    # ------------------------------------------------------------------ registration
    def register(
        self,
        type_id: str,
        provider: ProviderFunc,
        *,
        format: str | None = None,
        name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        override: bool = False,
    ) -> ProviderRef:
        key = (type_id, format)
        if not override and key in self._providers:
            raise ValueError(f"Provider already registered for {type_id!r} with format {format!r}.")
        ref = ProviderRef(
            type_id=type_id,
            format=format,
            name=name or provider.__name__,
            func=provider,
            metadata=metadata or {},
        )
        self._providers[key] = ref
        return ref

    def unregister(self, type_id: str, format: str | None = None) -> None:
        self._providers.pop((type_id, format), None)

    # ------------------------------------------------------------------ lookup
    def get(self, type_id: str, format: str | None = None) -> ProviderRef | None:
        key = (type_id, format)
        if key in self._providers:
            return self._providers[key]
        fallback_key = (type_id, None)
        return self._providers.get(fallback_key)

    def available(self) -> Iterable[ProviderRef]:
        return self._providers.values()

    def clear(self) -> None:
        self._providers.clear()

    # ------------------------------------------------------------------ plugins
    def register_plugin(self, plugin: Any) -> None:
        """Register a plugin object and invoke its provider hook."""

        self._plugin_manager.register(plugin)
        self._plugin_manager.hook.pfg_register_providers(registry=self)

    def load_entrypoint_plugins(self, group: str = "pydantic_fixturegen") -> None:
        """Load plugins defined via Python entry points and invoke hooks."""

        entry_points = metadata.entry_points()
        selector = getattr(entry_points, "select", None)
        if selector is not None:
            entries: Iterable[Any] = selector(group=group)
        else:  # pragma: no cover - Python <3.10 fallback
            entries = cast(Iterable[Any], entry_points.get(group, []))

        for entry in entries:
            plugin = entry.load()
            self.register_plugin(plugin)


__all__ = ["ProviderRegistry", "ProviderRef", "ProviderFunc"]
