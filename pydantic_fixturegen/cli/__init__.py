"""Command line interface for pydantic-fixturegen."""

from __future__ import annotations

import typer

from .doctor import app as doctor_app
from .gen import app as gen_app
from .gen.explain import app as explain_app
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
app.add_typer(
    doctor_app,
    name="doctor",
    help="Inspect models for coverage and risks.",
)
app.add_typer(
    explain_app,
    name="explain",
    help="Explain generation strategies per model field.",
)

__all__ = ["app"]
