"""Grouping for generation-related CLI commands."""

from __future__ import annotations

import typer

from .json import register as register_json


app = typer.Typer(help="Generate data artifacts from Pydantic models.")

register_json(app)

__all__ = ["app"]
