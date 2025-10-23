"""CLI command for listing Pydantic models."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.core.introspect import DiscoveryMethod, IntrospectionResult, discover

PATH_ARGUMENT = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Python module file(s) to inspect.",
)

INCLUDE_OPTION = typer.Option(
    None,
    "--include",
    "-i",
    help="Comma-separated glob pattern(s) of fully-qualified model names to include.",
)

EXCLUDE_OPTION = typer.Option(
    None,
    "--exclude",
    "-e",
    help="Comma-separated glob pattern(s) of fully-qualified model names to exclude.",
)

PUBLIC_OPTION = typer.Option(
    False,
    "--public-only",
    help="Only list public models (respects __all__ when defined).",
)

AST_OPTION = typer.Option(
    False,
    "--ast",
    help="Use AST discovery only (no imports executed).",
)

HYBRID_OPTION = typer.Option(
    False,
    "--hybrid",
    help="Combine AST and safe import discovery.",
)

TIMEOUT_OPTION = typer.Option(
    5.0,
    "--timeout",
    min=0.1,
    help="Timeout in seconds for safe import execution.",
)

MEMORY_LIMIT_OPTION = typer.Option(
    256,
    "--memory-limit-mb",
    min=1,
    help="Memory limit in megabytes for safe import subprocess.",
)


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")



def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> DiscoveryMethod:
    if ast_mode and hybrid_mode:
        raise typer.BadParameter("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


def _execute_list_command(
    path: Path,
    include: str | None,
    exclude: str | None,
    public_only: bool,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
) -> None:
    method = _resolve_method(ast_mode, hybrid_mode)

    result = discover(
        [path],
        method=method,
        include=_split_patterns(include),
        exclude=_split_patterns(exclude),
        public_only=public_only,
        safe_import_timeout=timeout,
        safe_import_memory_limit_mb=memory_limit_mb,
    )
    _render_result(result)


def list_models(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: Path = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    public_only: bool = PUBLIC_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
) -> None:
    _ = ctx  # unused
    _execute_list_command(
        path=path,
        include=include,
        exclude=exclude,
        public_only=public_only,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )


app.callback(invoke_without_command=True)(list_models)


def _render_result(result: IntrospectionResult) -> None:
    for warning in result.warnings:
        if warning.strip():
            typer.secho(f"warning: {warning.strip()}", err=True, fg=typer.colors.YELLOW)

    if result.errors:
        for error in result.errors:
            typer.secho(f"error: {error}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not result.models:
        typer.echo("No models discovered.")
        return

    for model in result.models:
        typer.echo(f"{model.qualname} [{model.discovery}]")


def _split_patterns(option_value: str | None) -> list[str]:
    if not option_value:
        return []
    return [pattern.strip() for pattern in option_value.split(",") if pattern.strip()]
