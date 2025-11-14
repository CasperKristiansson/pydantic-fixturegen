from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen.core import openapi as openapi_mod
from pydantic_fixturegen.core.errors import DiscoveryError


def test_parse_route_value_accepts_space_and_colon() -> None:
    spec = openapi_mod.parse_route_value("GET /users")
    assert spec.method == "GET" and spec.path == "/users"

    spec = openapi_mod.parse_route_value("post:/items")
    assert spec.method == "POST" and spec.path == "/items"

    with pytest.raises(ValueError):
        openapi_mod.parse_route_value("users")


def _sample_document() -> dict[str, object]:
    return {
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
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                }
            }
        },
    }


def test_select_openapi_schemas_all_routes() -> None:
    document = _sample_document()
    selection = openapi_mod.select_openapi_schemas(document, routes=None)

    assert selection.schemas == ("User",)
    assert selection.routes[0].path == "/users"
    assert selection.document["paths"]


def test_select_openapi_schemas_unknown_route() -> None:
    document = _sample_document()
    route = openapi_mod.RouteSpec(method="GET", path="/missing")
    with pytest.raises(DiscoveryError):
        openapi_mod.select_openapi_schemas(document, routes=[route])


def test_load_openapi_document_requires_file(tmp_path: Path, monkeypatch) -> None:
    doc_path = tmp_path / "doc.yaml"
    doc_path.write_text(
        "openapi: 3.1.0\npaths: {}\ncomponents:\n  schemas:\n    User: {}\n",
        encoding="utf-8",
    )
    document = openapi_mod.load_openapi_document(doc_path)
    assert document["openapi"] == "3.1.0"

    with pytest.raises(DiscoveryError):
        openapi_mod.load_openapi_document(tmp_path / "missing.yaml")
