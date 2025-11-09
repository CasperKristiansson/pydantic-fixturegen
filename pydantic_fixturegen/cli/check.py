"""CLI command for validating configuration and discovery without generating outputs."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import typer

from pydantic_fixturegen.core.config import ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, PFGError

from .gen._common import (  # shared helpers
    JSON_ERRORS_OPTION,
    DiscoveryMethod,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)

PATH_ARGUMENT = typer.Argument(
    ...,
    help="Python module path to validate discovery against.",
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

JSON_OUT_OPTION = typer.Option(
    None,
    "--json-out",
    help="Validate that the provided JSON/JSONL output path is writable.",
)

FIXTURES_OUT_OPTION = typer.Option(
    None,
    "--fixtures-out",
    help="Validate that the provided pytest fixtures output path is writable.",
)

SCHEMA_OUT_OPTION = typer.Option(
    None,
    "--schema-out",
    help="Validate that the provided JSON Schema output path is writable.",
)


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def check(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
    fixtures_out: Path | None = FIXTURES_OUT_OPTION,
    schema_out: Path | None = SCHEMA_OUT_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx
    try:
        _execute_check(
            target=path,
            include=include,
            exclude=exclude,
            ast_mode=_as_bool(ast_mode),
            hybrid_mode=_as_bool(hybrid_mode),
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
            json_out=json_out,
            fixtures_out=fixtures_out,
            schema_out=schema_out,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
    except ConfigError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)


app.callback(invoke_without_command=True)(check)


def _execute_check(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
    json_out: Path | None,
    fixtures_out: Path | None,
    schema_out: Path | None,
) -> None:
    target_path = Path(target)
    if not target_path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not target_path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    load_config(root=Path.cwd())

    clear_module_cache()

    method = _resolve_method(ast_mode, hybrid_mode)
    discovery = discover_models(
        target_path,
        include=split_patterns(include),
        exclude=split_patterns(exclude),
        method=method,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            typer.secho(f"warning: {warning.strip()}", err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    for model_info in discovery.models:
        try:
            load_model_class(model_info)
        except RuntimeError as exc:
            raise DiscoveryError(str(exc)) from exc

    _validate_output_targets(
        [
            (json_out, "JSON output"),
            (fixtures_out, "pytest fixtures output"),
            (schema_out, "schema output"),
        ]
    )

    typer.secho("Configuration OK", fg=typer.colors.GREEN)
    typer.echo(f"Discovered {len(discovery.models)} model(s) for validation.")

    if any(path is not None for path in (json_out, fixtures_out, schema_out)):
        typer.echo("Emitter destinations verified.")

    typer.echo("Check complete. No issues detected.")


def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> DiscoveryMethod:
    if ast_mode and hybrid_mode:
        raise DiscoveryError("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


def _validate_output_targets(targets: Iterable[tuple[Path | None, str]]) -> None:
    problems: list[str] = []
    for path, label in targets:
        if path is None:
            continue
        issues = _validate_output_path(Path(path), label)
        problems.extend(issues)

    if problems:
        message = "; ".join(problems)
        raise DiscoveryError(message)


def _validate_output_path(path: Path, label: str) -> list[str]:
    issues: list[str] = []
    if path.exists() and path.is_dir():
        issues.append(f"{label} '{path}' points to a directory; expected a file path.")
        return issues

    parent = path.parent if path.parent != path else path
    if not parent.exists():
        issues.append(f"Parent directory for {label} '{parent}' does not exist.")
        return issues

    if not parent.is_dir():
        issues.append(f"Parent path for {label} '{parent}' is not a directory.")
        return issues

    if not os.access(parent, os.W_OK):
        issues.append(f"Parent directory for {label} '{parent}' is not writable.")

    return issues


__all__ = ["app", "ConfigError", "DiscoveryError"]
