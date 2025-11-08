"""CLI command for inspecting project health."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, get_origin

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.extra_types import (
    describe_extra_annotation,
)
from pydantic_fixturegen.core.extra_types import (
    resolve_type_id as resolve_extra_type_id,
)
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldSummary, summarize_model_fields
from pydantic_fixturegen.core.strategies import StrategyBuilder, StrategyResult, UnionStrategy
from pydantic_fixturegen.plugins.loader import get_plugin_manager

from .gen._common import (
    JSON_ERRORS_OPTION,
    DiscoveryMethod,
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

FAIL_ON_GAPS_OPTION = typer.Option(
    None,
    "--fail-on-gaps",
    min=0,
    help="Exit with code 2 when uncovered fields exceed this number (errors only).",
)


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")


@dataclass
class ModelReport:
    model: type[BaseModel]
    coverage: tuple[int, int]
    issues: list[str]
    gaps: list[FieldGap] = field(default_factory=list)


@dataclass(slots=True)
class GapInfo:
    type_name: str
    reason: str
    remediation: str
    severity: Literal["error", "warning"]


@dataclass(slots=True)
class FieldGap:
    model: type[BaseModel]
    field: str
    info: GapInfo

    @property
    def qualified_field(self) -> str:
        return f"{self.model.__name__}.{self.field}"


@dataclass(slots=True)
class TypeGapSummary:
    type_name: str
    reason: str
    remediation: str
    severity: Literal["error", "warning"]
    occurrences: int
    fields: list[str]


@dataclass(slots=True)
class GapSummary:
    summaries: list[TypeGapSummary]
    total_error_fields: int
    total_warning_fields: int


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
    fail_on_gaps: int | None = FAIL_ON_GAPS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        gap_summary = _execute_doctor(
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
        return

    if fail_on_gaps is not None and gap_summary.total_error_fields > fail_on_gaps:
        raise typer.Exit(code=2)


app.callback(invoke_without_command=True)(doctor)


def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> DiscoveryMethod:
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
) -> GapSummary:
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
        empty_summary = GapSummary(summaries=[], total_error_fields=0, total_warning_fields=0)
        return empty_summary

    registry = create_default_registry(load_plugins=True)
    builder = StrategyBuilder(registry, plugin_manager=get_plugin_manager())

    reports: list[ModelReport] = []
    all_gaps: list[FieldGap] = []
    for model_info in discovery.models:
        try:
            model_cls = load_model_class(model_info)
        except RuntimeError as exc:
            raise DiscoveryError(str(exc)) from exc
        model_report = _analyse_model(model_cls, builder)
        reports.append(model_report)
        all_gaps.extend(model_report.gaps)

    gap_summary = _summarize_gaps(all_gaps)
    _render_report(reports, gap_summary)
    return gap_summary


def _analyse_model(model: type[BaseModel], builder: StrategyBuilder) -> ModelReport:
    total_fields = 0
    covered_fields = 0
    issues: list[str] = []
    field_gaps: list[FieldGap] = []

    summaries = summarize_model_fields(model)

    for field_name, model_field in model.model_fields.items():
        total_fields += 1
        summary = summaries[field_name]
        try:
            strategy = builder.build_field_strategy(
                model,
                field_name,
                model_field.annotation,
                summary,
                field_info=model_field,
            )
        except ValueError as exc:
            message = str(exc)
            issues.append(f"{model.__name__}.{field_name}: [error] {message}")
            field_gaps.append(
                FieldGap(
                    model=model,
                    field=field_name,
                    info=GapInfo(
                        type_name=summary.type,
                        reason=message,
                        remediation=(
                            "Register a custom provider or configure an override for this field."
                        ),
                        severity="error",
                    ),
                )
            )
            continue

        covered, gap_infos = _strategy_status(summary, strategy)
        if covered:
            covered_fields += 1
        for gap_info in gap_infos:
            severity_label = "warning" if gap_info.severity == "warning" else "error"
            issues.append(f"{model.__name__}.{field_name}: [{severity_label}] {gap_info.reason}")
            field_gaps.append(FieldGap(model=model, field=field_name, info=gap_info))

    return ModelReport(
        model=model,
        coverage=(covered_fields, total_fields),
        issues=issues,
        gaps=field_gaps,
    )


def _strategy_status(summary: FieldSummary, strategy: StrategyResult) -> tuple[bool, list[GapInfo]]:
    if isinstance(strategy, UnionStrategy):
        gap_infos: list[GapInfo] = []
        covered = True
        for choice in strategy.choices:
            choice_ok, choice_gaps = _strategy_status(choice.summary, choice)
            if not choice_ok:
                covered = False
            gap_infos.extend(choice_gaps)
        return covered, gap_infos

    gaps: list[GapInfo] = []
    if strategy.enum_values:
        return True, gaps

    if summary.type in {"model", "dataclass"}:
        return True, gaps

    base_annotation = _resolve_annotation_origin(summary.annotation)
    extra_label = describe_extra_annotation(summary.annotation) if summary.annotation else None
    extra_supported = bool(base_annotation and resolve_extra_type_id(base_annotation))

    if strategy.provider_ref is None:
        if extra_label and not extra_supported:
            gaps.append(
                GapInfo(
                    type_name="pydantic-extra-types",
                    reason=f"No provider available for {extra_label}.",
                    remediation=(
                        "Install the missing dependency or register a provider for this type."
                    ),
                    severity="error",
                )
            )
        else:
            gaps.append(
                GapInfo(
                    type_name=summary.type,
                    reason=f"No provider registered for type '{summary.type}'.",
                    remediation=(
                        "Register a custom provider or configure an override for this field."
                    ),
                    severity="error",
                )
            )
        return False, gaps

    if extra_label and not extra_supported:
        gaps.append(
            GapInfo(
                type_name="pydantic-extra-types",
                reason=f"Field falls back to generic providers for {extra_label}.",
                remediation=(
                    "Pin a supported provider or override the field to avoid generic values."
                ),
                severity="error",
            )
        )

    if summary.type == "any":
        gaps.append(
            GapInfo(
                type_name="any",
                reason="Falls back to generic `Any` provider.",
                remediation="Define a provider for this shape or narrow the field annotation.",
                severity="warning",
            )
        )
    return True, gaps


def _resolve_annotation_origin(annotation: Any | None) -> Any | None:
    target = annotation
    while True:
        origin = get_origin(target)
        if origin is None:
            break
        target = origin
    return target


def _summarize_gaps(field_gaps: Iterable[FieldGap]) -> GapSummary:
    grouped: dict[tuple[str, str, str, str], list[str]] = {}
    error_fields = 0
    warning_fields = 0

    for gap in field_gaps:
        key = (
            gap.info.severity,
            gap.info.type_name,
            gap.info.reason,
            gap.info.remediation,
        )
        grouped.setdefault(key, []).append(gap.qualified_field)
        if gap.info.severity == "error":
            error_fields += 1
        else:
            warning_fields += 1

    summaries = [
        TypeGapSummary(
            type_name=type_name,
            reason=reason,
            remediation=remediation,
            severity=cast(Literal["error", "warning"], severity),
            occurrences=len(fields),
            fields=sorted(fields),
        )
        for (severity, type_name, reason, remediation), fields in grouped.items()
    ]
    summaries.sort(
        key=lambda item: (
            0 if item.severity == "error" else 1,
            item.type_name,
            item.reason,
        )
    )

    return GapSummary(
        summaries=summaries,
        total_error_fields=error_fields,
        total_warning_fields=warning_fields,
    )


def _render_report(reports: list[ModelReport], gap_summary: GapSummary) -> None:
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

    if not gap_summary.summaries:
        typer.echo("Type coverage gaps: none")
        return

    typer.echo("Type coverage gaps:")
    for summary in gap_summary.summaries:
        level = "WARNING" if summary.severity == "warning" else "ERROR"
        typer.echo(f"  - {summary.type_name}: {summary.reason} [{level}]")
        typer.echo(f"    Fields ({summary.occurrences}):")
        for field_name in summary.fields:
            typer.echo(f"      • {field_name}")
        typer.echo(f"    Remediation: {summary.remediation}")
    typer.echo("")


__all__ = ["app", "get_plugin_manager"]
