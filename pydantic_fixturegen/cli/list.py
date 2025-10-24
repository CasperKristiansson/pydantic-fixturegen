"""CLI command for listing Pydantic models."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError, UnsafeImportError
from pydantic_fixturegen.core.introspect import DiscoveryMethod, IntrospectionResult, discover

from .gen._common import JSON_ERRORS_OPTION, render_cli_error, split_patterns

PATH_ARGUMENT = typer.Argument(
    ...,
    help="Python module file to inspect.",
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
    help="Only list public models (respects __all__).",
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
        raise DiscoveryError("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


def list_models(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    public_only: bool = PUBLIC_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        _execute_list_command(
            target=path,
            include=include,
            exclude=exclude,
            public_only=public_only,
            ast_mode=ast_mode,
            hybrid_mode=hybrid_mode,
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)


app.callback(invoke_without_command=True)(list_models)


def _execute_list_command(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    public_only: bool,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
) -> None:
    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

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


def _render_result(result: IntrospectionResult) -> None:
    for warning in result.warnings:
        if warning.strip():
            typer.secho(f"warning: {warning.strip()}", err=True, fg=typer.colors.YELLOW)

    if result.errors:
        message = "; ".join(result.errors)
        if any("network" in error.lower() for error in result.errors):
            raise UnsafeImportError(message)
        raise DiscoveryError(message)

    if not result.models:
        typer.echo("No models discovered.")
        return

    for model in result.models:
        typer.echo(f"{model.qualname} [{model.discovery}]")


def _split_patterns(option_value: str | None) -> list[str]:
    return split_patterns(option_value)


__all__ = ["app"]
