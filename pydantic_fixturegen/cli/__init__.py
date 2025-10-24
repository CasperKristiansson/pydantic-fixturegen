"""Command line interface for pydantic-fixturegen."""

from __future__ import annotations

import typer

from .gen import app as gen_app
from .list import app as list_app

app = typer.Typer(help="pydantic-fixturegen command line interface")
app.add_typer(
    list_app,
    name="list",
    help="List Pydantic models from modules or files.",
    invoke_without_command=True,
)
app.add_typer(
    gen_app,
    name="gen",
    help="Generate artifacts for discovered models.",
)

__all__ = ["app"]
