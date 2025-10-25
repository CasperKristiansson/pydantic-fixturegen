"""Command line interface for pydantic-fixturegen."""

from __future__ import annotations

import builtins
from importlib import import_module

import typer
from typer.main import get_command


def _load_typer(import_path: str) -> typer.Typer:
    module_name, attr = import_path.split(":", 1)
    module = import_module(module_name)
    loaded = getattr(module, attr)
    if not isinstance(loaded, typer.Typer):
        raise TypeError(f"Attribute {attr!r} in module {module_name!r} is not a Typer app.")
    return loaded


def _invoke(import_path: str, ctx: typer.Context) -> None:
    sub_app = _load_typer(import_path)
    command = get_command(sub_app)
    args = builtins.list(ctx.args)
    result = command.main(
        args=args,
        prog_name=ctx.command_path,
        standalone_mode=False,
    )
    if isinstance(result, int):
        raise typer.Exit(code=result)


app = typer.Typer(
    help="pydantic-fixturegen command line interface",
    invoke_without_command=True,
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:  # noqa: D401
    if ctx.invoked_subcommand is None:
        _invoke("pydantic_fixturegen.cli.list:app", ctx)
        raise typer.Exit()


def _proxy(name: str, import_path: str, help_text: str) -> None:
    context_settings = {
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }

    @app.command(name, context_settings=context_settings)
    def command(ctx: typer.Context) -> None:
        _invoke(import_path, ctx)

    command.__doc__ = help_text


_proxy(
    "list",
    "pydantic_fixturegen.cli.list:app",
    "List Pydantic models from modules or files.",
)
_proxy(
    "gen",
    "pydantic_fixturegen.cli.gen:app",
    "Generate artifacts for discovered models.",
)
_proxy(
    "init",
    "pydantic_fixturegen.cli.init:app",
    "Scaffold configuration and directories for new projects.",
)
_proxy(
    "doctor",
    "pydantic_fixturegen.cli.doctor:app",
    "Inspect models for coverage and risks.",
)
_proxy(
    "explain",
    "pydantic_fixturegen.cli.gen.explain:app",
    "Explain generation strategies per model field.",
)

__all__ = ["app"]
