from __future__ import annotations

import json
from collections import UserDict
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core import openapi
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.openapi import ComponentGraph


def _fake_yaml(loader=None, dumper=None) -> SimpleNamespace:
    return SimpleNamespace(
        safe_load=loader or (lambda text: json.loads(text)),
        safe_dump=dumper or (lambda data, sort_keys=True: json.dumps(data, sort_keys=sort_keys)),
    )


def _document() -> dict[str, object]:
    return {
        "paths": {
            "/users": {
                "get": {
                    "parameters": [{"$ref": "#/components/parameters/Locale"}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    },
                }
            },
            "/stats": {
                "post": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Stats"}
                                }
                            }
                        }
                    }
                }
            },
        },
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "address": {"$ref": "#/components/schemas/Address"},
                        "profile": {"$ref": "#/components/schemas/Profile"},
                    },
                },
                "Address": {"type": "object"},
                "Profile": {"type": "object"},
                "Stats": {"type": "object"},
            },
            "parameters": {
                "Locale": {"name": "locale", "in": "query"},
            },
        },
    }


def test_parse_route_value_accepts_multiple_delimiters() -> None:
    first = openapi.parse_route_value("GET /users")
    assert first.method == "GET" and first.path == "/users"

    second = openapi.parse_route_value("post:/items")
    assert second.method == "POST" and second.path == "/items"

    with pytest.raises(ValueError):
        openapi.parse_route_value("/users")
    with pytest.raises(ValueError):
        openapi.parse_route_value("GET users")


def test_load_openapi_document_validates_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(DiscoveryError):
        openapi.load_openapi_document(missing)

    doc_path = tmp_path / "doc.yaml"
    doc_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(openapi, "yaml", None, raising=False)
    with pytest.raises(DiscoveryError):
        openapi.load_openapi_document(doc_path)


def test_load_and_dump_openapi_document_with_stub_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"paths": {}}
    doc_path = tmp_path / "doc.yaml"
    doc_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(openapi, "yaml", _fake_yaml(), raising=False)
    loaded = openapi.load_openapi_document(doc_path)
    assert loaded == payload

    dumped = openapi.dump_document(payload)
    assert dumped.decode("utf-8").startswith("{")


def test_select_openapi_schemas_handles_unknown_routes() -> None:
    doc = _document()
    route = openapi.RouteSpec(method="DELETE", path="/missing")
    with pytest.raises(DiscoveryError) as exc:
        openapi.select_openapi_schemas(doc, routes=[route])
    assert exc.value.details and "routes" in exc.value.details


def test_select_openapi_schemas_requires_refs() -> None:
    minimal = {
        "paths": {
            "/bare": {
                "get": {
                    "responses": {
                        "200": {"content": {"application/json": {"schema": {"type": "object"}}}}
                    }
                }
            }
        }
    }
    with pytest.raises(DiscoveryError):
        openapi.select_openapi_schemas(minimal, routes=None)


def test_select_openapi_schemas_trims_document() -> None:
    doc = _document()
    route = openapi.RouteSpec(method="GET", path="/users")
    selection = openapi.select_openapi_schemas(doc, routes=[route])

    assert selection.routes == (route,)
    assert selection.schemas == ("Address", "Profile", "User")
    assert list(selection.document["paths"].keys()) == ["/users"]
    components = selection.document["components"]
    assert set(components["schemas"].keys()) == {"User", "Address", "Profile"}
    assert "Stats" not in components["schemas"]
    assert selection.fingerprint().startswith("GET /users")


def test_select_openapi_schemas_previous_routes_used_when_none() -> None:
    doc = _document()
    selection = openapi.select_openapi_schemas(doc, routes=None)
    assert len(selection.routes) == 2
    assert "Stats" in selection.schemas


def test_parse_route_value_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        openapi.parse_route_value("   ")


def test_load_openapi_document_rejects_non_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_path = tmp_path / "doc.yaml"
    doc_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(openapi, "yaml", _fake_yaml(), raising=False)
    with pytest.raises(DiscoveryError):
        openapi.load_openapi_document(doc_path)


def test_select_openapi_schemas_requires_paths_mapping() -> None:
    with pytest.raises(DiscoveryError):
        openapi.select_openapi_schemas({"paths": []}, routes=None)


def test_dump_document_requires_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openapi, "yaml", None, raising=False)
    with pytest.raises(DiscoveryError):
        openapi.dump_document({})


def test_enumerate_routes_handles_invalid_entries() -> None:
    doc = {
        "paths": {
            "/broken": "oops",
            "/skip": {"trace": {"summary": "ignored"}},
            "/also": {"get": []},
        }
    }
    assert openapi._enumerate_routes(doc) == set()


def test_component_graph_handles_missing_components() -> None:
    doc = {
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    },
                    "headers": {"X-Trace": {"$ref": "#/components/headers/TraceCtx"}},
                    "parameters": [{"$ref": "#/components/parameters/Locale"}],
                }
            },
            "/unused": {"get": []},
        },
        "components": {
            "schemas": {"User": {"properties": {"friend": {"$ref": "#/components/schemas/User"}}}},
            "parameters": [],
            "headers": {},
        },
    }
    graph = openapi._build_component_graph(
        doc,
        [openapi.RouteSpec("GET", "/users"), openapi.RouteSpec("GET", "/unused")],
    )
    assert "User" in graph.schemas


def test_component_graph_handles_absent_components_section() -> None:
    doc = {
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": [],
    }
    graph = openapi._build_component_graph(doc, [openapi.RouteSpec("GET", "/users")])
    assert graph.schemas == set()


def test_trimmed_document_handles_custom_mapping() -> None:
    document = UserDict(
        {
            "paths": {
                "/include": {"get": {"responses": {}}},
                "/bad": "oops",
                "/also": {"get": []},
            },
            "components": {"schemas": []},
        }
    )
    routes = [
        openapi.RouteSpec("GET", "/include"),
        openapi.RouteSpec("GET", "/bad"),
        openapi.RouteSpec("GET", "/also"),
    ]
    graph = ComponentGraph(schemas=set(), components={"schemas": {"Include"}})
    trimmed = openapi._build_trimmed_document(document, routes, graph)
    assert list(trimmed["paths"].keys()) == ["/include"]
    assert trimmed.get("components") == {}
