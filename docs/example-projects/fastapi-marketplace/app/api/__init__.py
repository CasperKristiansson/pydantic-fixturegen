"""Routers imported lazily so FastAPI stays optional for doc readers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from fastapi import FastAPI


def create_app() -> FastAPI:
    """Instantiate FastAPI and include routers.

    FastAPI is imported lazily so `pfg` discovery can import models without the
    dependency installed. Users following the example project should install
    the `fastapi` extra listed in `pyproject.toml` before calling this helper.
    """

    from fastapi import FastAPI  # noqa: PLC0415

    from .routes import catalog, orders

    app = FastAPI(title="Marketplace API", version="0.1.0")
    app.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
    app.include_router(orders.router, prefix="/orders", tags=["orders"])
    return app
