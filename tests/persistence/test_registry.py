from __future__ import annotations

from pydantic_fixturegen.persistence.registry import PersistenceRegistry


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
