"""Utilities for importing FastAPI apps and introspecting routes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Literal, cast

from pydantic import BaseModel

from ..core.errors import DiscoveryError

PayloadShape = Literal["single", "list", "dict"]


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
    request_shape: PayloadShape
    response_shape: PayloadShape


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
            request_model, request_shape = _extract_payload(route.body_field)
            response_model, response_shape = _extract_payload(route.secure_cloned_response_field)
            yield FastAPIRouteSpec(
                path=route.path,
                method=method.upper(),
                name=route.name or _slugify_route(method, route.path),
                request_model=request_model,
                response_model=response_model,
                request_shape=request_shape,
                response_shape=response_shape,
            )


def _extract_payload(field: Any) -> tuple[type[BaseModel] | None, PayloadShape]:
    if field is None:
        return None, "single"
    candidate = getattr(field, "type_", None) or getattr(field, "outer_type_", None)
    return _normalize_model(candidate)


def _normalize_model(candidate: Any) -> tuple[type[BaseModel] | None, PayloadShape]:
    if candidate is None:
        return None, "single"
    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
        return candidate, "single"
    origin = getattr(candidate, "__origin__", None)
    if origin in {list, set, tuple}:
        args = getattr(candidate, "__args__", ())
        model = next(
            (arg for arg in args if isinstance(arg, type) and issubclass(arg, BaseModel)),
            None,
        )
        return model, "list"
    if origin is dict:
        args = getattr(candidate, "__args__", ())
        if len(args) == 2:
            value_type = cast(tuple[Any, Any], args)[1]
            model, _ = _normalize_model(value_type)
            return model, "dict"
        return None, "dict"
    return None, "single"


def _slugify_route(method: str, path: str) -> str:
    slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    slug = slug or "root"
    return f"{method.lower()}_{slug}"


__all__ = ["FastAPIRouteSpec", "PayloadShape", "import_fastapi_app", "iter_route_specs"]
