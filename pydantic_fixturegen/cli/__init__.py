"""Command line interface for pydantic-fixturegen."""

from __future__ import annotations

import builtins
from importlib import import_module

import typer
from typer.main import get_command

import pydantic_fixturegen.cli._typer_compat  # noqa: F401
from pydantic_fixturegen._warnings import apply_warning_filters
from pydantic_fixturegen.cli import anonymize as anonymize_cli
from pydantic_fixturegen.cli import fastapi as fastapi_cli
from pydantic_fixturegen.cli import polyfactory as polyfactory_cli
from pydantic_fixturegen.cli import schema as schema_cli
from pydantic_fixturegen.logging import DEFAULT_VERBOSITY_INDEX, LOG_LEVEL_ORDER, get_logger

DOCS_URL = "https://pydantic-fixturegen.kitgrid.dev/"

apply_warning_filters()


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
    _append_docs_footer(command)
    args = builtins.list(ctx.args)
    result = command.main(
        args=args,
        prog_name=ctx.command_path,
        standalone_mode=False,
    )
    if isinstance(result, int):
        raise typer.Exit(code=result)


app = typer.Typer(
    help=f"pydantic-fixturegen command line interface\n\nDocs: {DOCS_URL}",
    invoke_without_command=True,
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase log verbosity."),
    quiet: int = typer.Option(0, "--quiet", "-q", count=True, help="Decrease log verbosity."),
    log_json: bool = typer.Option(False, "--log-json", help="Emit structured JSON logs."),
) -> None:  # noqa: D401
    logger = get_logger()
    level_index = DEFAULT_VERBOSITY_INDEX + verbose - quiet
    level_index = max(0, min(level_index, len(LOG_LEVEL_ORDER) - 1))
    level_name = LOG_LEVEL_ORDER[level_index]
    logger.configure(level=level_name, json_mode=log_json)

    if ctx.invoked_subcommand is None:
        _invoke("pydantic_fixturegen.cli.list:app", ctx)
        raise typer.Exit()


def _proxy(name: str, import_path: str, help_text: str) -> None:
    context_settings = {
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }

    def _command(ctx: typer.Context) -> None:
        _invoke(import_path, ctx)

    decorator = app.command(
        name,
        context_settings=context_settings,
        help=help_text,
        add_help_option=False,
    )
    decorator(_command)


def _append_docs_footer(command: typer.main.TyperCommand) -> None:
    if getattr(command, "_pfg_docs_patched", False):
        return
    footer = f"\n\nDocs: {DOCS_URL}"
    help_text = command.help or ""
    command.help = f"{help_text}{footer}" if help_text else f"Docs: {DOCS_URL}"
    setattr(command, "_pfg_docs_patched", True)
    children = getattr(command, "commands", None)
    if isinstance(children, dict):
        for child in children.values():
            _append_docs_footer(child)


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
    "diff",
    "pydantic_fixturegen.cli.diff:app",
    "Regenerate artifacts in-memory and compare against existing files.",
)
_proxy(
    "check",
    "pydantic_fixturegen.cli.check:app",
    "Validate configuration, discovery, and emitter destinations without generating artifacts.",
)
_proxy(
    "init",
    "pydantic_fixturegen.cli.init:app",
    "Scaffold configuration and directories for new projects.",
)
_proxy(
    "plugin",
    "pydantic_fixturegen.cli.plugin:app",
    "Scaffold provider plugin projects.",
)
_proxy(
    "doctor",
    "pydantic_fixturegen.cli.doctor:app",
    "Inspect models for coverage and risks.",
)
_proxy(
    "coverage",
    "pydantic_fixturegen.cli.coverage:app",
    "Generate coverage reports for models and overrides.",
)
_proxy(
    "lock",
    "pydantic_fixturegen.cli.lock:app",
    "Generate coverage lockfiles for CI verification.",
)
_proxy(
    "verify",
    "pydantic_fixturegen.cli.verify:app",
    "Compare current coverage against the stored lockfile.",
)
_proxy(
    "snapshot",
    "pydantic_fixturegen.cli.snapshot:app",
    "Verify or refresh stored artifact snapshots.",
)
_proxy(
    "explain",
    "pydantic_fixturegen.cli.gen.explain:app",
    "Explain generation strategies per model field.",
)
_proxy(
    "persist",
    "pydantic_fixturegen.cli.persist:app",
    "Send generated payloads to persistence handlers.",
)

app.add_typer(schema_cli.app, name="schema")
app.add_typer(fastapi_cli.app, name="fastapi")
app.add_typer(anonymize_cli.app, name="anonymize")
app.add_typer(polyfactory_cli.app, name="polyfactory")

_append_docs_footer(get_command(app))

__all__ = ["app"]
