"""Mock FastAPI server powered by pydantic-fixturegen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..core.generate import GenerationConfig, InstanceGenerator
from ..core.seed import SeedManager
from .loader import import_fastapi_app, iter_route_specs


def _require_fastapi_objects() -> Any:
    from fastapi import FastAPI

    return FastAPI


def build_mock_app(
    *,
    target: str,
    seed: int | None = None,
    dependency_overrides: list[tuple[Callable[..., Any], Callable[..., Any]]] | None = None,
) -> Any:
    """Return a FastAPI app that mocks the target application."""

    FastAPI = _require_fastapi_objects()
    source_app = import_fastapi_app(target)
    if dependency_overrides:
        for original, override in dependency_overrides:
            source_app.dependency_overrides[original] = override

    mock_app = FastAPI(title=f"Mock server for {getattr(source_app, 'title', target)}")

    normalized_seed = SeedManager(seed=seed).normalized_seed if seed is not None else None
    generator = InstanceGenerator(config=GenerationConfig(seed=normalized_seed))

    for spec in iter_route_specs(source_app):
        payload = _build_response_factory(generator, spec.response_model)

        async def handler(payload_fn: Callable[[], Any] = payload) -> Any:
            return payload_fn()

        mock_app.add_api_route(
            path=spec.path,
            endpoint=handler,
            methods=[spec.method],
            name=f"mock_{spec.name}",
        )

    return mock_app


def _build_response_factory(
    generator: InstanceGenerator, model: type[BaseModel] | None
) -> Callable[[], Any]:
    if model is None:
        return lambda: {"ok": True}

    def factory() -> Any:
        instance = generator.generate_one(model)
        if instance is None:
            return {}
        return instance.model_dump(mode="json")

    return factory


__all__ = ["build_mock_app"]
