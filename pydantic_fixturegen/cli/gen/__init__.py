"""Grouping for generation-related CLI commands."""

from __future__ import annotations

import typer

from .json import register as register_json
from .schema import register as register_schema


app = typer.Typer(help="Generate data artifacts from Pydantic models.")

register_json(app)
register_schema(app)

__all__ = ["app"]
