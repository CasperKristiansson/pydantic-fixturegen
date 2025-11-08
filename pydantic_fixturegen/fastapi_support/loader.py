"""Utilities for importing FastAPI apps and introspecting routes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from pydantic import BaseModel

from ..core.errors import DiscoveryError


def _require_fastapi() -> Any:
    try:
        import fastapi
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DiscoveryError(
            "FastAPI integration requires the 'fastapi' extra. Install it via "
            "`pip install pydantic-fixturegen[fastapi]`."
        ) from exc
    return fastapi


@dataclass(slots=True)
class FastAPIRouteSpec:
    path: str
    method: str
    name: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel] | None


def import_fastapi_app(target: str) -> Any:
    """Import a FastAPI/Starlette application using ``module:attr`` syntax."""

    if ":" not in target:
        raise DiscoveryError("FastAPI targets must be provided as module:attr (e.g. 'app:app').")
    module_name, attr = target.split(":", 1)
    module = import_module(module_name)
    app = getattr(module, attr, None)
    if app is None:
        raise DiscoveryError(
            f"Attribute '{attr}' not found in module '{module_name}'.",
            details={"module": module_name, "attribute": attr},
        )
    if not hasattr(app, "routes"):
        raise DiscoveryError("Target does not look like a FastAPI application.")
    return app


def iter_route_specs(app: Any) -> Iterable[FastAPIRouteSpec]:
    """Yield simplified metadata for FastAPI routes."""

    _require_fastapi()
    routing_module = import_module("fastapi.routing")
    APIRoute = routing_module.APIRoute

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods or {"GET"}
        for method in sorted(methods):
            if method.upper() in {"HEAD", "OPTIONS"}:
                continue
            request_model = _extract_model(route.body_field)
            response_model = _extract_model(route.secure_cloned_response_field)
            yield FastAPIRouteSpec(
                path=route.path,
                method=method.upper(),
                name=route.name or _slugify_route(method, route.path),
                request_model=request_model,
                response_model=response_model,
            )


def _extract_model(field: Any) -> type[BaseModel] | None:
    if field is None:
        return None
    candidate = getattr(field, "type_", None) or getattr(field, "outer_type_", None)
    model = _normalize_model(candidate)
    return model


def _normalize_model(candidate: Any) -> type[BaseModel] | None:
    if candidate is None:
        return None
    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
        return candidate
    origin = getattr(candidate, "__origin__", None)
    if origin is list or origin is set:
        args = getattr(candidate, "__args__", ())
        return next(
            (arg for arg in args if isinstance(arg, type) and issubclass(arg, BaseModel)),
            None,
        )
    if origin is dict:
        args = getattr(candidate, "__args__", ())
        if len(args) == 2:
            value_type = cast(tuple[Any, Any], args)[1]
            return _normalize_model(value_type)
    return None


def _slugify_route(method: str, path: str) -> str:
    slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    slug = slug or "root"
    return f"{method.lower()}_{slug}"


__all__ = ["FastAPIRouteSpec", "import_fastapi_app", "iter_route_specs"]
