from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.persistence import registry as registry_mod
from pydantic_fixturegen.persistence.registry import PersistenceRegistry


class _ConfigurableHandler:
    def __init__(self, *, marker: str, extra: bool | None = None) -> None:
        self.marker = marker
        self.extra = extra

    def persist_batch(self, batch):  # noqa: ANN001
        return None


def test_registry_exposes_builtins() -> None:
    registry = PersistenceRegistry()
    available = registry.available()
    assert "http-post" in available
    assert "sqlite-json" in available


def test_registry_registers_sync_handler() -> None:
    registry = PersistenceRegistry()
    registry.register_from_path(
        "capture",
        "tests.persistence_helpers:SyncCaptureHandler",
    )

    handler, kind, options = registry.create("capture", {})
    assert kind == "sync"
    assert options == {}
    assert hasattr(handler, "persist_batch")


def test_registry_registers_async_handler() -> None:
    registry = PersistenceRegistry()
    registry.register_from_path(
        "async-capture",
        "tests.persistence_helpers:AsyncCaptureHandler",
    )

    handler, kind, _ = registry.create("async-capture", {})
    assert kind == "async"
    assert hasattr(handler, "persist_batch")


def test_registry_prevents_duplicate_registrations() -> None:
    registry = PersistenceRegistry()
    factory = registry_mod.PersistenceHandlerFactory(
        name="custom",
        factory=lambda _: object(),
        kind="sync",
    )
    registry.register(factory)
    with pytest.raises(ValueError):
        registry.register(factory)


def test_registry_allows_override() -> None:
    registry = PersistenceRegistry()
    factory = registry_mod.PersistenceHandlerFactory(
        name="custom",
        factory=lambda _: "first",
    )
    registry.register(factory)
    registry.register(
        registry_mod.PersistenceHandlerFactory(
            name="custom",
            factory=lambda _: SimpleNamespace(persist_batch=lambda batch: None),
            kind="sync",
        ),
        override=True,
    )

    handler, kind, _ = registry.create("custom", {})
    assert hasattr(handler, "persist_batch")
    assert kind == "sync"


def test_registry_merges_default_options() -> None:
    registry = PersistenceRegistry()
    registry.register_from_path(
        "namespaced",
        "tests.persistence.test_registry:_ConfigurableHandler",
        default_options={"marker": "base"},
    )

    handler, _, options = registry.create("namespaced", {"extra": True})
    assert options["marker"] == "base"
    assert options["extra"] is True
    assert handler.marker == "base"


def test_resolve_target_errors_for_missing_attribute() -> None:
    with pytest.raises(ValueError):
        registry_mod._resolve_target("tests.persistence_helpers:Missing")


def test_resolve_target_requires_path() -> None:
    with pytest.raises(ValueError):
        registry_mod._resolve_target("")


def test_resolve_target_supports_dot_paths() -> None:
    target = registry_mod._resolve_target("tests.persistence.test_registry._ConfigurableHandler")
    assert target.__name__ == _ConfigurableHandler.__name__


def test_registry_create_unknown_handler() -> None:
    registry = PersistenceRegistry()
    with pytest.raises(KeyError):
        registry.create("missing")


def test_registry_register_plugin_invokes_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = PersistenceRegistry()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        registry_mod,
        "register_plugin",
        lambda plugin: calls.append({"plugin": plugin}),
    )
    registry._plugin_manager = SimpleNamespace(
        hook=SimpleNamespace(
            pfg_register_persistence_handlers=lambda **kwargs: calls.append(kwargs)
        )
    )
    registry.register_plugin("demo")
    assert any(call.get("plugin") == "demo" for call in calls)
    assert any(call.get("registry") is registry for call in calls if "registry" in call)


def test_registry_load_entrypoint_plugins_invokes_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = PersistenceRegistry()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(registry_mod, "load_entrypoint_plugins", lambda group, force: [object()])
    registry._plugin_manager = SimpleNamespace(
        hook=SimpleNamespace(
            pfg_register_persistence_handlers=lambda **kwargs: calls.append(kwargs)
        )
    )
    registry.load_entrypoint_plugins(force=True)
    assert calls and calls[0]["registry"] is registry


def test_detect_handler_kind_distinguishes_async() -> None:
    class AsyncHandler:
        async def persist_batch(self, batch):  # noqa: ANN001
            await asyncio.sleep(0)

    class SyncHandler:
        def persist_batch(self, batch):  # noqa: ANN001
            return None

    assert registry_mod._detect_handler_kind(AsyncHandler()) == "async"
    assert registry_mod._detect_handler_kind(SyncHandler()) == "sync"

    with pytest.raises(TypeError):
        registry_mod._detect_handler_kind(SimpleNamespace())
