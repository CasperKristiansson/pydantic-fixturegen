from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.fastapi_support.loader import FastAPIRouteSpec
from pydantic_fixturegen.fastapi_support.mock import (
    _build_response_factory,
    build_mock_app,
)

from fastapi import FastAPI  # noqa: F401


class _DummyGenerator:
    def __init__(self, value: BaseModel | None) -> None:
        self._value = value

    def generate_one(self, model: type[BaseModel]) -> BaseModel | None:
        return self._value


class _SampleModel(BaseModel):
    id: int
    name: str


def test_build_response_factory_without_model_returns_default() -> None:
    generator = _DummyGenerator(_SampleModel(id=1, name="example"))
    factory = _build_response_factory(generator, None, "single")

    assert factory() == {"ok": True}


def test_build_response_factory_handles_sequence_wrapping() -> None:
    generator = _DummyGenerator(_SampleModel(id=1, name="generated"))
    list_factory = _build_response_factory(generator, _SampleModel, "list")

    assert list_factory() == [{"id": 1, "name": "generated"}]


def test_build_response_factory_handles_missing_instance_by_shape() -> None:
    generator = _DummyGenerator(None)
    dict_factory = _build_response_factory(generator, _SampleModel, "dict")

    assert dict_factory() == {}


def test_build_mock_app_registers_routes_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded_factories: list[tuple[type[BaseModel] | None, str]] = []

    def fake_factory(
        generator: Any,
        model: type[BaseModel] | None,
        shape: str,
    ) -> Callable[[], dict[str, Any]]:
        recorded_factories.append((model, shape))
        return lambda: {"payload": shape}

    monkeypatch.setattr(
        "pydantic_fixturegen.fastapi_support.mock._build_response_factory",
        fake_factory,
    )

    class DummyFastAPI:
        def __init__(self, title: str) -> None:
            self.title = title
            self.dependency_overrides: dict[Any, Any] = {}
            self.routes: list[SimpleNamespace] = []

        def add_api_route(
            self,
            *,
            path: str,
            endpoint: Callable[..., Any],
            methods: list[str],
            name: str,
        ) -> None:
            self.routes.append(
                SimpleNamespace(path=path, endpoint=endpoint, methods=methods, name=name)
            )

    source_app = SimpleNamespace(
        title="source",
        dependency_overrides={},
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.fastapi_support.mock._require_fastapi_objects",
        lambda: DummyFastAPI,
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.fastapi_support.mock.import_fastapi_app",
        lambda target: source_app,
    )

    specs = [
        FastAPIRouteSpec(
            path="/items",
            method="GET",
            name="list_items",
            request_model=None,
            response_model=_SampleModel,
            request_shape="single",
            response_shape="dict",
        ),
    ]
    monkeypatch.setattr(
        "pydantic_fixturegen.fastapi_support.mock.iter_route_specs",
        lambda app: specs,
    )

    original_dep = object()
    override_dep = object()
    app = build_mock_app(
        target="module:app",
        dependency_overrides=[(original_dep, override_dep)],
    )

    assert source_app.dependency_overrides[original_dep] is override_dep
    assert recorded_factories == [(_SampleModel, "dict")]
    assert len(app.routes) == 1
    route = app.routes[0]
    assert route.path == "/items"
    assert route.methods == ["GET"]
    assert route.name == "mock_list_items"
    assert asyncio.run(route.endpoint()) == {"payload": "dict"}
