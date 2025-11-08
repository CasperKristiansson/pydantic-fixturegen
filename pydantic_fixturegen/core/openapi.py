"""Helpers for analysing OpenAPI documents for schema generation."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DiscoveryError

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None


HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "patch",
    "options",
    "head",
}


@dataclass(frozen=True)
class RouteSpec:
    """Normalised HTTP method + path filter."""

    method: str
    path: str

    def fingerprint(self) -> str:
        return f"{self.method} {self.path}"


@dataclass(slots=True)
class ComponentGraph:
    """Resolved component references for a set of routes."""

    schemas: set[str]
    components: dict[str, set[str]]


@dataclass(slots=True)
class OpenAPISelection:
    """Schema names and trimmed document for ingestion."""

    schemas: tuple[str, ...]
    document: dict[str, Any]
    routes: tuple[RouteSpec, ...]

    def fingerprint(self) -> str:
        route_sig = "|".join(route.fingerprint() for route in self.routes) or "ALL"
        schema_sig = ",".join(self.schemas)
        return f"{route_sig}::{schema_sig}"


def parse_route_value(raw: str) -> RouteSpec:
    """Parse CLI route input into a structured spec."""

    candidate = raw.strip()
    if not candidate:
        raise ValueError("route cannot be empty")
    if " " in candidate:
        method, path = candidate.split(None, 1)
    elif ":" in candidate:
        method, path = candidate.split(":", 1)
    else:
        raise ValueError("route must include an HTTP method and path")
    method = method.strip().upper()
    path = path.strip()
    if not path.startswith("/"):
        raise ValueError("route paths must start with '/'")
    return RouteSpec(method=method, path=path)


def load_openapi_document(path: Path) -> dict[str, Any]:
    """Load a YAML/JSON OpenAPI document into a mapping."""

    if not path.exists():
        raise DiscoveryError(f"OpenAPI document '{path}' not found.", details={"path": str(path)})
    if yaml is None:
        raise DiscoveryError(
            "Loading OpenAPI documents requires PyYAML. Install the 'openapi' extra "
            "via `pip install pydantic-fixturegen[openapi]`.",
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DiscoveryError("OpenAPI documents must decode to a mapping.")
    return data


def select_openapi_schemas(
    document: Mapping[str, Any],
    routes: Sequence[RouteSpec] | None,
) -> OpenAPISelection:
    """Determine which schemas are required for the selected routes."""

    available_routes = _enumerate_routes(document)
    if not available_routes:
        raise DiscoveryError("OpenAPI document does not define any routable paths.")
    if routes:
        normalized = tuple(routes)
        unknown = [
            route.fingerprint()
            for route in normalized
            if (route.path, route.method.lower()) not in available_routes
        ]
        if unknown:
            raise DiscoveryError(
                "OpenAPI document does not define the requested route(s).",
                details={"routes": unknown},
            )
    else:
        normalized = tuple(
            RouteSpec(method=method.upper(), path=path) for path, method in sorted(available_routes)
        )

    graph = _build_component_graph(document, normalized)
    if not graph.schemas:
        raise DiscoveryError(
            "Selected routes did not reference any reusable schemas via $ref.",
            hint=(
                "Reference components under '#/components/schemas/*' "
                "to enable fixture generation."
            ),
        )

    trimmed = _build_trimmed_document(document, normalized, graph)
    return OpenAPISelection(
        schemas=tuple(sorted(graph.schemas)),
        document=trimmed,
        routes=normalized,
    )


def dump_document(document: Mapping[str, Any]) -> bytes:
    """Return a deterministic YAML dump for caching."""

    if yaml is None:
        raise DiscoveryError(
            "Loading OpenAPI documents requires PyYAML. Install the 'openapi' extra "
            "via `pip install pydantic-fixturegen[openapi]`.",
        )
    rendered: str = yaml.safe_dump(document, sort_keys=True)
    return rendered.encode("utf-8")


# --------------------------------------------------------------------------- internals
def _enumerate_routes(document: Mapping[str, Any]) -> set[tuple[str, str]]:
    paths = document.get("paths")
    if not isinstance(paths, Mapping):
        return set()
    available: set[tuple[str, str]] = set()
    for path, entry in paths.items():
        if not isinstance(entry, Mapping):
            continue
        for method, operation in entry.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if isinstance(operation, Mapping):
                available.add((path, method.lower()))
    return available


def _build_component_graph(
    document: Mapping[str, Any],
    routes: Sequence[RouteSpec],
) -> ComponentGraph:
    components = document.get("components")
    if not isinstance(components, Mapping):
        components = {}

    initial_refs: list[tuple[str, str]] = []
    for route in routes:
        op = (
            document.get("paths", {})
            .get(route.path, {})
            .get(route.method.lower())
        )
        if not isinstance(op, Mapping):
            continue
        initial_refs.extend(_iter_component_refs(op))

    resolved: dict[str, set[str]] = {}
    schema_names: set[str] = set()
    queue: list[tuple[str, str]] = list(initial_refs)
    seen: set[tuple[str, str]] = set()
    while queue:
        comp_type, name = queue.pop()
        key = (comp_type, name)
        if key in seen:
            continue
        seen.add(key)
        resolved.setdefault(comp_type, set()).add(name)
        section = components.get(comp_type)
        if not isinstance(section, Mapping):
            continue
        definition = section.get(name)
        if definition is None:
            continue
        if comp_type == "schemas":
            schema_names.add(name)
        queue.extend(_iter_component_refs(definition))

    return ComponentGraph(schemas=schema_names, components=resolved)


def _build_trimmed_document(
    document: Mapping[str, Any],
    routes: Sequence[RouteSpec],
    graph: ComponentGraph,
) -> dict[str, Any]:
    trimmed = copy.deepcopy(document)
    if isinstance(trimmed, dict):
        trimmed_dict: dict[str, Any] = trimmed
    else:
        trimmed_dict = dict(trimmed)

    # Trim paths down to the requested routes.
    requested = {(route.path, route.method.lower()) for route in routes}
    filtered_paths: dict[str, Any] = {}
    for path, method in requested:
        path_entry = document.get("paths", {}).get(path)
        if not isinstance(path_entry, Mapping):
            continue
        op = path_entry.get(method)
        if not isinstance(op, Mapping):
            continue
        filtered_entry = filtered_paths.setdefault(path, {})
        filtered_entry[method] = copy.deepcopy(op)
    trimmed_dict["paths"] = filtered_paths

    components = document.get("components")
    if isinstance(components, Mapping) and graph.components:
        filtered_components: dict[str, Any] = {}
        for comp_type, names in graph.components.items():
            section = components.get(comp_type)
            if not isinstance(section, Mapping):
                continue
            filtered_components[comp_type] = {
                name: copy.deepcopy(section[name])
                for name in names
                if name in section
            }
        trimmed_dict["components"] = filtered_components

    return trimmed_dict


def _iter_component_refs(node: Any) -> Iterator[tuple[str, str]]:
    if isinstance(node, Mapping):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/"):
            parts = ref.strip("#/").split("/")
            if len(parts) >= 3:
                yield parts[1], parts[-1]
        for value in node.values():
            yield from _iter_component_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_component_refs(value)


__all__ = [
    "OpenAPISelection",
    "RouteSpec",
    "dump_document",
    "load_openapi_document",
    "parse_route_value",
    "select_openapi_schemas",
]
