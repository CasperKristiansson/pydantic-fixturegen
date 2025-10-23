from __future__ import annotations

from typing import Any

import pytest
from pydantic_fixturegen.core.providers import ProviderRef, ProviderRegistry
from pydantic_fixturegen.plugins.hookspecs import hookimpl


def test_register_and_lookup_provider() -> None:
    registry = ProviderRegistry()

    def provider(_: Any) -> str:
        return "value"

    ref = registry.register("string", provider, name="basic")

    assert isinstance(ref, ProviderRef)
    fetched = registry.get("string")
    assert fetched is ref
    assert fetched.func(None) == "value"

    with pytest.raises(ValueError):
        registry.register("string", provider)

    registry.unregister("string")
    assert registry.get("string") is None


def test_register_with_format_and_override() -> None:
    registry = ProviderRegistry()

    registry.register("string", lambda _: "plain")
    with_format = registry.register("string", lambda _: "email", format="email")

    assert registry.get("string", "email") is with_format
    assert registry.get("string") is not None

    def replacement(_: Any) -> str:
        return "override"

    registry.register("string", replacement, override=True)
    assert registry.get("string").func(None) == "override"
    assert list(registry.available())
    registry.clear()
    assert list(registry.available()) == []


def test_register_plugin_invokes_hook() -> None:
    registry = ProviderRegistry()

    class Plugin:
        @hookimpl
        def pfg_register_providers(self, registry: ProviderRegistry) -> None:
            registry.register("int", lambda _: 42, name="answer")

    registry.register_plugin(Plugin())

    provider = registry.get("int")
    assert provider is not None
    assert provider.func(None) == 42


def test_load_entrypoint_plugins_handles_missing_group(monkeypatch) -> None:
    registry = ProviderRegistry()

    class DummyPlugin:
        @hookimpl
        def pfg_register_providers(self, registry: ProviderRegistry) -> None:
            registry.register("bool", lambda _: True)

    class DummyEntryPoint:
        def load(self) -> object:
            return DummyPlugin()

    class DummyEntryPoints:
        @staticmethod
        def select(group: str):
            assert group == "pydantic_fixturegen"
            return [DummyEntryPoint()]

    monkeypatch.setattr("importlib.metadata.entry_points", lambda: DummyEntryPoints())

    registry.load_entrypoint_plugins()
    assert registry.get("bool").func(None) is True
