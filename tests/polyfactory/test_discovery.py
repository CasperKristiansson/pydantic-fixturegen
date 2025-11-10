from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.polyfactory_support import discovery
from pydantic_fixturegen.polyfactory_support.discovery import (
    _env_flag,
    _polyfactory_supports_pydantic,
)


class SampleModel(BaseModel):
    value: int


class DummyLogger:
    def __init__(self) -> None:
        self.warnings: list[dict[str, Any]] = []
        self.infos: list[dict[str, Any]] = []

    def warn(self, message: str, **kwargs: Any) -> None:
        self.warnings.append({"message": message, **kwargs})

    def info(self, message: str, **kwargs: Any) -> None:
        self.infos.append({"message": message, **kwargs})


@pytest.fixture(autouse=True)
def reset_polyfactory_base(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeFactoryBase:  # noqa: D401 - simple shim
        """Shim used in place of the optional polyfactory dependency."""

    monkeypatch.setattr(discovery, "POLYFACTORY_MODEL_FACTORY", FakeFactoryBase)


def test_discover_polyfactory_bindings_registers_and_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_modules: dict[str, ModuleType] = {}

    def fake_load(name: str) -> ModuleType | None:
        if name == "missing.module":
            return None
        module = ModuleType(name)

        class Factory(discovery.POLYFACTORY_MODEL_FACTORY):  # type: ignore[misc]
            __model__ = SampleModel

        module.SampleFactory = Factory
        loaded_modules[name] = module
        return module

    monkeypatch.setattr(discovery, "_load_module", fake_load)
    logger = DummyLogger()

    bindings = discovery.discover_polyfactory_bindings(
        model_classes=[SampleModel],
        discovery_modules=["pkg.factories"],
        extra_modules=["missing.module"],
        logger=logger,
    )

    assert len(bindings) == 1
    assert bindings[0].model is SampleModel
    assert logger.warnings and "missing.module" in logger.warnings[0]["module"]
    assert logger.infos and logger.infos[0]["model"] == "SampleModel"


def test_discover_polyfactory_bindings_prefers_first_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(name: str) -> ModuleType:
        module = ModuleType(name)

        class BaseFactory(discovery.POLYFACTORY_MODEL_FACTORY):  # type: ignore[misc]
            __model__ = SampleModel

        class AlternateFactory(discovery.POLYFACTORY_MODEL_FACTORY):  # type: ignore[misc]
            __model__ = SampleModel

        module.First = BaseFactory
        module.Second = AlternateFactory
        return module

    monkeypatch.setattr(discovery, "_load_module", fake_load)
    bindings = discovery.discover_polyfactory_bindings(
        model_classes=[SampleModel],
        discovery_modules=["pkg.factories"],
        extra_modules=[],
        logger=DummyLogger(),
    )

    assert len(bindings) == 1
    assert bindings[0].label.endswith(".BaseFactory")


def test_discover_polyfactory_bindings_handles_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "POLYFACTORY_MODEL_FACTORY", None)
    bindings = discovery.discover_polyfactory_bindings(
        model_classes=[SampleModel],
        discovery_modules=[],
        extra_modules=[],
        logger=DummyLogger(),
    )
    assert bindings == []


def test_env_flag_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFG_TEST_FLAG", "Yes")
    try:
        assert _env_flag("PFG_TEST_FLAG") is True
    finally:
        monkeypatch.delenv("PFG_TEST_FLAG", raising=False)


def test_polyfactory_supports_pydantic_true() -> None:
    class FriendlyFactory:
        """Factory stub that allows subclassing."""

    assert _polyfactory_supports_pydantic(FriendlyFactory) is True


def test_polyfactory_supports_pydantic_false() -> None:
    class HostileFactory:
        def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: D401 - short helper
            """Raise whenever a subclass is created to simulate polyfactory rejecting models."""

            raise RuntimeError("fail subclassing")

    assert _polyfactory_supports_pydantic(HostileFactory) is False
