"""Registry for persistence handlers."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from pydantic_fixturegen.plugins.loader import (
    get_plugin_manager,
    load_entrypoint_plugins,
    register_plugin,
)

from .handlers import (
    AsyncHttpPostPersistenceHandler,
    HttpPostPersistenceHandler,
    SQLiteJSONPersistenceHandler,
)
from .models import HandlerKind

HandlerFactoryFunc = Callable[[Mapping[str, Any]], Any]


@dataclass(slots=True)
class PersistenceHandlerFactory:
    """Descriptor for a registered persistence handler."""

    name: str
    factory: HandlerFactoryFunc
    kind: HandlerKind | None = None
    description: str | None = None
    default_options: Mapping[str, Any] = field(default_factory=dict)
    source: str | None = None


class PersistenceRegistry:
    """Registry storing available persistence handlers."""

    def __init__(self) -> None:
        self._factories: dict[str, PersistenceHandlerFactory] = {}
        self._plugin_manager = get_plugin_manager()
        self._register_builtins()

    def register(self, factory: PersistenceHandlerFactory, *, override: bool = False) -> None:
        if not override and factory.name in self._factories:
            raise ValueError(f"Handler '{factory.name}' is already registered.")
        self._factories[factory.name] = factory

    def register_from_path(
        self,
        name: str,
        path: str,
        *,
        kind: HandlerKind | None = None,
        default_options: Mapping[str, Any] | None = None,
        override: bool = False,
    ) -> None:
        def _factory(options: Mapping[str, Any]) -> Any:
            target = _resolve_target(path)
            params = dict(options)
            if isinstance(target, type):
                return target(**params)
            if callable(target):
                return target(**params)
            return target

        self.register(
            PersistenceHandlerFactory(
                name=name,
                factory=_factory,
                kind=kind,
                default_options=MappingProxyType(dict(default_options or {})),
                description=f"Custom handler from {path}",
                source=path,
            ),
            override=override,
        )

    def available(self) -> Mapping[str, PersistenceHandlerFactory]:
        return MappingProxyType(self._factories)

    def create(
        self,
        name: str,
        options: Mapping[str, Any] | None = None,
    ) -> tuple[Any, HandlerKind, Mapping[str, Any]]:
        factory = self._factories.get(name)
        if factory is None:
            raise KeyError(f"Unknown persistence handler '{name}'.")
        merged_options = dict(factory.default_options)
        if options:
            merged_options.update(options)
        handler = factory.factory(MappingProxyType(merged_options))
        kind = factory.kind or _detect_handler_kind(handler)
        return handler, kind, MappingProxyType(merged_options)

    def register_plugin(self, plugin: Any) -> None:
        register_plugin(plugin)
        self._plugin_manager.hook.pfg_register_persistence_handlers(registry=self)

    def load_entrypoint_plugins(
        self,
        group: str = "pydantic_fixturegen",
        *,
        force: bool = False,
    ) -> None:
        plugins = load_entrypoint_plugins(group, force=force)
        if not plugins:
            return
        self._plugin_manager.hook.pfg_register_persistence_handlers(registry=self)

    def _register_builtins(self) -> None:
        self.register(
            PersistenceHandlerFactory(
                name="http-post",
                factory=lambda opts: HttpPostPersistenceHandler(**dict(opts)),
                kind="sync",
                description="Send batches to an HTTP endpoint as JSON.",
            )
        )
        self.register(
            PersistenceHandlerFactory(
                name="http-post-async",
                factory=lambda opts: AsyncHttpPostPersistenceHandler(**dict(opts)),
                kind="async",
                description="Async HTTP persistence using a background executor.",
            )
        )
        self.register(
            PersistenceHandlerFactory(
                name="sqlite-json",
                factory=lambda opts: SQLiteJSONPersistenceHandler(**dict(opts)),
                kind="sync",
                description="Insert JSON payloads into a SQLite table.",
            )
        )


def _resolve_target(path: str) -> Any:
    if not path:
        raise ValueError("Handler paths must be non-empty.")
    module_name: str
    attr_path: str
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise ValueError(f"Handler path '{path}' could not be resolved (missing '{part}').")
        target = getattr(target, part)
    return target


def _detect_handler_kind(handler: Any) -> HandlerKind:
    persist = getattr(handler, "persist_batch", None)
    if persist is None:
        raise TypeError("Persistence handlers must define a 'persist_batch' method.")
    func = getattr(persist, "__func__", persist)
    if inspect.iscoroutinefunction(func):
        return "async"
    return "sync"


__all__ = ["PersistenceRegistry", "PersistenceHandlerFactory"]
