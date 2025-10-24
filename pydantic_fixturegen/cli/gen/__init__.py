"""Grouping for generation-related CLI commands."""

from __future__ import annotations

import typer

from .explain import app as explain_app
from .fixtures import register as register_fixtures
from .json import register as register_json
from .schema import register as register_schema

app = typer.Typer(help="Generate data artifacts from Pydantic models.")

register_json(app)
register_schema(app)
register_fixtures(app)
app.add_typer(
    explain_app,
    name="explain",
    help="Explain generation strategy per model field.",
)

__all__ = ["app"]
