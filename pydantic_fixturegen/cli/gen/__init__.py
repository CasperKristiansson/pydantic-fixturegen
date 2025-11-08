"""Grouping for generation-related CLI commands."""

from __future__ import annotations

import typer

from .examples import register as register_examples
from .explain import app as explain_app
from .fixtures import register as register_fixtures
from .json import register as register_json
from .openapi import register as register_openapi
from .polyfactory import register as register_polyfactory
from .schema import register as register_schema
from .strategies import register as register_strategies

app = typer.Typer(help="Generate data artifacts from Pydantic models.")

register_json(app)
register_openapi(app)
register_schema(app)
register_examples(app)
register_fixtures(app)
register_strategies(app)
register_polyfactory(app)
app.add_typer(
    explain_app,
    name="explain",
    help="Explain generation strategy per model field.",
)

__all__ = ["app"]
