"""Grouping for generation-related CLI commands."""

from __future__ import annotations

import typer

from .fixtures import register as register_fixtures
from .json import register as register_json
from .schema import register as register_schema

app = typer.Typer(help="Generate data artifacts from Pydantic models.")

register_json(app)
register_schema(app)
register_fixtures(app)

__all__ = ["app"]
