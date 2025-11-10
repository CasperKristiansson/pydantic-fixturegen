from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.core.generate import InstanceGenerator
from pydantic_fixturegen.polyfactory_support import (
    PolyfactoryBinding,
    attach_polyfactory_bindings,
    discover_polyfactory_bindings,
)
from pydantic_fixturegen.polyfactory_support import discovery as discovery_mod
from pydantic_fixturegen.polyfactory_support.discovery import POLYFACTORY_MODEL_FACTORY


class _FallbackModelFactory:
    """Minimal stand-in used when polyfactory isn't available."""

    __check_model__ = False

    def __class_getitem__(cls, _item):  # pragma: no cover - typing convenience
        return cls

    @classmethod
    def seed_random(cls, seed: int | None) -> None:  # pragma: no cover - stateful no-op
        cls._seed = seed  # type: ignore[attr-defined]

    @classmethod
    def build(cls):
        model = getattr(cls, "__model__", None)
        if model is None:
            raise RuntimeError("Fallback factories require a __model__ attribute.")
        return model()


ModelFactory = POLYFACTORY_MODEL_FACTORY or _FallbackModelFactory


@pytest.fixture(autouse=True)
def _patch_discovery_model_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    if POLYFACTORY_MODEL_FACTORY is not None:
        return
    monkeypatch.setattr(
        discovery_mod,
        "POLYFACTORY_MODEL_FACTORY",
        ModelFactory,
        raising=False,
    )


class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def info(self, message: str, **kwargs: Any) -> None:  # pragma: no cover - best-effort
        self.messages.append((message, kwargs))

    def warn(self, message: str, **kwargs: Any) -> None:  # pragma: no cover - best-effort
        self.messages.append((message, kwargs))


class Widget(BaseModel):
    name: str = "fixturegen"


class WidgetFactory(ModelFactory[Widget]):
    __model__ = Widget
    __check_model__ = False

    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Widget:  # noqa: ARG003
        return Widget(name="polyfactory")


def test_attach_polyfactory_bindings_delegates_generation() -> None:
    generator = InstanceGenerator()
    binding = PolyfactoryBinding(model=Widget, factory=WidgetFactory, source="test.WidgetFactory")
    attach_polyfactory_bindings(generator, (binding,))

    result = generator.generate_one(Widget)
    assert isinstance(result, Widget)
    assert result.name == "polyfactory"


def test_discover_polyfactory_bindings_picks_up_factories() -> None:
    bindings = discover_polyfactory_bindings(
        model_classes=[Widget],
        discovery_modules=[__name__],
        extra_modules=(),
        logger=_FakeLogger(),
    )

    assert any(binding.factory is WidgetFactory for binding in bindings)
