from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.fastapi_support import loader


class _SampleModel(BaseModel):
    id: int


class _OtherModel(BaseModel):
    value: str


def test_import_fastapi_app_validates_target_format() -> None:
    with pytest.raises(DiscoveryError):
        loader.import_fastapi_app("module_only")


def test_import_fastapi_app_requires_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("demo_app")
    monkeypatch.setitem(sys.modules, "demo_app", module)

    with pytest.raises(DiscoveryError) as exc:
        loader.import_fastapi_app("demo_app:app")

    assert "Attribute" in str(exc.value)


def test_import_fastapi_app_requires_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("demo_app")
    module.app = object()
    monkeypatch.setitem(sys.modules, "demo_app", module)

    with pytest.raises(DiscoveryError) as exc:
        loader.import_fastapi_app("demo_app:app")

    assert "does not look like" in str(exc.value)


def test_iter_route_specs_exposes_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_require_fastapi", lambda: None)

    class DummyAPIRoute:
        def __init__(self, **attrs: Any) -> None:
            for key, value in attrs.items():
                setattr(self, key, value)

    def fake_import_module(name: str) -> Any:  # pragma: no cover - fallback branch unused
        if name == "fastapi.routing":
            return SimpleNamespace(APIRoute=DummyAPIRoute)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(loader, "import_module", fake_import_module)

    body_field = SimpleNamespace(outer_type_=list[_SampleModel])
    fallback_field = SimpleNamespace(type_=_SampleModel)

    route_with_fallback = DummyAPIRoute(
        methods={"get", "HEAD"},
        path="/items/{item_id}",
        name="",
        body_field=body_field,
        secure_cloned_response_field=None,
        response_field=fallback_field,
        response_model=None,
    )

    route_with_declared = DummyAPIRoute(
        methods={"post"},
        path="/items",
        name="create_item",
        body_field=None,
        secure_cloned_response_field=None,
        response_field=None,
        response_model=dict[str, _OtherModel],
    )

    app = SimpleNamespace(routes=[SimpleNamespace(), route_with_fallback, route_with_declared])

    specs = list(loader.iter_route_specs(app))

    assert len(specs) == 2
    first = specs[0]
    assert first.method == "GET"
    assert first.name == "get_items_item_id"
    assert first.request_shape == "list"
    assert first.response_model is _SampleModel
    assert first.response_shape == "single"

    second = specs[1]
    assert second.method == "POST"
    assert second.request_model is None
    assert second.response_model is _OtherModel
    assert second.response_shape == "dict"


def test_normalize_model_handles_none_and_unparameterized() -> None:
    assert loader._normalize_model(None) == (None, "single")
    partial_dict = SimpleNamespace(__origin__=dict, __args__=(str,))
    assert loader._normalize_model(partial_dict) == (None, "dict")


def test_normalize_model_handles_generics() -> None:
    value = loader._normalize_model(list[_SampleModel])
    assert value == (_SampleModel, "list")
    dict_value = loader._normalize_model(dict[str, _OtherModel])
    assert dict_value == (_OtherModel, "dict")
