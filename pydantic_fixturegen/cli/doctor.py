"""CLI command for inspecting project health."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldSummary, summarize_model_fields
from pydantic_fixturegen.core.strategies import StrategyBuilder, StrategyResult, UnionStrategy
from pydantic_fixturegen.plugins.loader import get_plugin_manager

from .gen._common import (
    JSON_ERRORS_OPTION,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)

PATH_ARGUMENT = typer.Argument(..., help="Path to a Python module containing Pydantic models.")

INCLUDE_OPTION = typer.Option(
    None,
    "--include",
    "-i",
    help="Comma-separated pattern(s) of fully-qualified model names to include.",
)

EXCLUDE_OPTION = typer.Option(
    None,
    "--exclude",
    "-e",
    help="Comma-separated pattern(s) of fully-qualified model names to exclude.",
)

AST_OPTION = typer.Option(False, "--ast", help="Use AST discovery only (no imports executed).")

HYBRID_OPTION = typer.Option(False, "--hybrid", help="Combine AST and safe import discovery.")

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


@dataclass
class ModelReport:
    model: type[BaseModel]
    coverage: tuple[int, int]
    issues: list[str]


def doctor(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        _execute_doctor(
            target=path,
            include=include,
            exclude=exclude,
            ast_mode=ast_mode,
            hybrid_mode=hybrid_mode,
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)


app.callback(invoke_without_command=True)(doctor)


def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> str:
    if ast_mode and hybrid_mode:
        raise DiscoveryError("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


def _execute_doctor(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
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

    clear_module_cache()

    method = _resolve_method(ast_mode, hybrid_mode)
    discovery = discover_models(
        path,
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
        typer.echo("No models discovered.")
        return

    registry = create_default_registry(load_plugins=True)
    builder = StrategyBuilder(registry, plugin_manager=get_plugin_manager())

    reports: list[ModelReport] = []
    for model_info in discovery.models:
        try:
            model_cls = load_model_class(model_info)
        except RuntimeError as exc:
            raise DiscoveryError(str(exc)) from exc
        reports.append(_analyse_model(model_cls, builder))

    _render_report(reports)


def _analyse_model(model: type[BaseModel], builder: StrategyBuilder) -> ModelReport:
    total_fields = 0
    covered_fields = 0
    issues: list[str] = []

    try:
        strategies = builder.build_model_strategies(model)
    except ValueError as exc:  # missing provider
        summaries = summarize_model_fields(model)
        message = str(exc)
        return ModelReport(
            model=model,
            coverage=(0, len(summaries)),
            issues=[message],
        )

    summaries = summarize_model_fields(model)

    for field_name, strategy in strategies.items():
        total_fields += 1
        summary = summaries[field_name]
        covered, field_issues = _strategy_status(summary, strategy)
        if covered:
            covered_fields += 1
        issues.extend(f"{model.__name__}.{field_name}: {msg}" for msg in field_issues)

    return ModelReport(model=model, coverage=(covered_fields, total_fields), issues=issues)


def _strategy_status(summary: FieldSummary, strategy: StrategyResult) -> tuple[bool, list[str]]:
    if isinstance(strategy, UnionStrategy):
        issue_messages: list[str] = []
        covered = True
        for choice in strategy.choices:
            choice_ok, choice_issues = _strategy_status(choice.summary, choice)
            if not choice_ok:
                covered = False
                issue_messages.extend(choice_issues)
        return covered, issue_messages

    messages: list[str] = []
    if strategy.enum_values:
        return True, messages

    if summary.type in {"model", "dataclass"}:
        return True, messages

    if strategy.provider_ref is None:
        messages.append(f"no provider for type '{summary.type}'")
        return False, messages

    if summary.type == "any":
        messages.append("falls back to generic type")
    return True, messages


def _render_report(reports: list[ModelReport]) -> None:
    for report in reports:
        covered, total = report.coverage
        coverage_pct = (covered / total * 100) if total else 100.0
        typer.echo(f"Model: {report.model.__module__}.{report.model.__name__}")
        typer.echo(f"  Coverage: {covered}/{total} fields ({coverage_pct:.0f}%)")
        if report.issues:
            typer.echo("  Issues:")
            for issue in report.issues:
                typer.echo(f"    - {issue}")
        else:
            typer.echo("  Issues: none")
        typer.echo("")


__all__ = ["app"]
