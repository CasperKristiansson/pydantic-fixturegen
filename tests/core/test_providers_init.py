from __future__ import annotations

from pydantic_fixturegen.core.providers import ProviderRegistry, create_default_registry


def test_create_default_registry_loads_plugins(monkeypatch) -> None:
    calls: list[str] = []

    def fake_loader(
        self: ProviderRegistry,
        group: str = "pydantic_fixturegen",
        *,
        force: bool = False,
    ) -> None:
        calls.append(f"{group}:{force}")

    monkeypatch.setattr(ProviderRegistry, "load_entrypoint_plugins", fake_loader, raising=True)

    registry = create_default_registry()

    assert calls == ["pydantic_fixturegen:False"]
    providers = {ref.type_id for ref in registry.available()}
    assert "string" in providers
    assert "float" in providers


def test_create_default_registry_skips_plugins_when_disabled(monkeypatch) -> None:
    calls: list[str] = []

    def fake_loader(
        self: ProviderRegistry,
        group: str = "pydantic_fixturegen",
        *,
        force: bool = False,
    ) -> None:
        calls.append("called")

    monkeypatch.setattr(ProviderRegistry, "load_entrypoint_plugins", fake_loader, raising=True)

    registry = create_default_registry(load_plugins=False)

    assert calls == []
    assert registry.get("string") is not None
    assert registry.get("float") is not None
