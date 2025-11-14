"""FastAPI entrypoint for the marketplace example."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

from .api import create_app

__all__ = ["create_app"]


def build_app() -> FastAPI:
    """Factory used by `uvicorn app:build_app` style commands."""

    return create_app()
