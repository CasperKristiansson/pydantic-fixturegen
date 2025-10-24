"""Provider registry for mapping types to value generators."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic_fixturegen.plugins.loader import (
    get_plugin_manager,
    load_entrypoint_plugins,
    register_plugin,
)

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
        self._plugin_manager = get_plugin_manager()

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

        register_plugin(plugin)
        self._plugin_manager.hook.pfg_register_providers(registry=self)

    def load_entrypoint_plugins(
        self,
        group: str = "pydantic_fixturegen",
        *,
        force: bool = False,
    ) -> None:
        """Load plugins defined via Python entry points and invoke hooks."""

        plugins = load_entrypoint_plugins(group, force=force)
        if not plugins:
            return
        self._plugin_manager.hook.pfg_register_providers(registry=self)


__all__ = ["ProviderRegistry", "ProviderRef", "ProviderFunc"]
