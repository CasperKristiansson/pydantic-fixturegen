"""CLI command for inspecting project health."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, get_origin

import typer

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.extra_types import describe_extra_annotation
from pydantic_fixturegen.core.extra_types import (
    resolve_type_id as resolve_extra_type_id,
)
from pydantic_fixturegen.core.openapi import (
    dump_document,
    load_openapi_document,
    parse_route_value,
    select_openapi_schemas,
)
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldSummary, summarize_model_fields
from pydantic_fixturegen.core.schema_ingest import SchemaIngester
from pydantic_fixturegen.core.seed_freeze import canonical_module_name
from pydantic_fixturegen.core.strategies import (
    Strategy,
    StrategyBuilder,
    StrategyResult,
    UnionStrategy,
)
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

PATH_ARGUMENT = typer.Argument(
    None,
    help="Path to a Python module containing Pydantic models.",
    show_default=False,
)

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

SCHEMA_OPTION = typer.Option(
    None,
    "--schema",
    help="Path to a JSON Schema document to analyse instead of a Python module.",
)

OPENAPI_OPTION = typer.Option(
    None,
    "--openapi",
    help="Path to an OpenAPI document to analyse.",
)

ROUTES_OPTION = typer.Option(
    None,
    "--route",
    help="Limit --openapi analysis to a specific HTTP method and path (e.g. 'GET /users').",
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


@dataclass(slots=True)
class FieldReport:
    name: str
    type_name: str
    provider: str | None
    covered: bool
    gaps: list[GapInfo] = field(default_factory=list)


@dataclass
class ModelReport:
    model: type[Any]
    coverage: tuple[int, int]
    issues: list[str]
    gaps: list[FieldGap] = field(default_factory=list)
    fields: list[FieldReport] = field(default_factory=list)


@dataclass(slots=True)
class GapInfo:
    type_name: str
    reason: str
    remediation: str
    severity: Literal["error", "warning"]


@dataclass(slots=True)
class FieldGap:
    model: type[Any]
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
    path: str | None = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    schema: Path | None = SCHEMA_OPTION,
    openapi: Path | None = OPENAPI_OPTION,
    routes: list[str] | None = ROUTES_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
    fail_on_gaps: int | None = FAIL_ON_GAPS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        target_path, auto_include = _prepare_doctor_target(
            path_arg=path,
            schema=schema,
            openapi=openapi,
            routes=routes,
        )

        include_segments: list[str] = []
        if include:
            include_segments.append(include)
        include_segments.extend(auto_include)
        include_value = ",".join(filter(None, include_segments)) if include_segments else None

        gap_summary = _execute_doctor(
            target=str(target_path),
            include=include_value,
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


def _prepare_doctor_target(
    *,
    path_arg: str | None,
    schema: Path | None,
    openapi: Path | None,
    routes: list[str] | None,
) -> tuple[Path, list[str]]:
    if routes and openapi is None:
        raise DiscoveryError("--route can only be used together with --openapi.")

    provided = sum(1 for value in (path_arg, schema, openapi) if value is not None)
    if provided == 0:
        raise DiscoveryError("Provide a module path, --schema, or --openapi.")
    if provided > 1:
        raise DiscoveryError("Choose only one of a module path, --schema, or --openapi.")

    if schema is not None:
        schema_path = schema.resolve()
        if not schema_path.exists():
            raise DiscoveryError(
                f"Schema file '{schema_path}' does not exist.",
                details={"path": str(schema_path)},
            )
        ingestion = SchemaIngester().ingest_json_schema(schema_path)
        return ingestion.path, []

    if openapi is not None:
        spec_path = openapi.resolve()
        if not spec_path.exists():
            raise DiscoveryError(
                f"OpenAPI document '{spec_path}' does not exist.",
                details={"path": str(spec_path)},
            )
        try:
            parsed_routes = [parse_route_value(value) for value in routes] if routes else None
        except ValueError as exc:
            raise DiscoveryError(str(exc)) from exc
        document = load_openapi_document(spec_path)
        selection = select_openapi_schemas(document, parsed_routes)
        ingestion = SchemaIngester().ingest_openapi(
            spec_path,
            document_bytes=dump_document(selection.document),
            fingerprint=selection.fingerprint(),
        )
        includes = [f"*.{name}" for name in selection.schemas]
        return ingestion.path, includes

    assert path_arg is not None
    return Path(path_arg), []


def _run_doctor_analysis(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
) -> tuple[list[ModelReport], GapSummary]:
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
        return [], empty_summary

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
    return reports, gap_summary


def _execute_doctor(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
    render: bool = True,
) -> GapSummary:
    reports, gap_summary = _run_doctor_analysis(
        target=target,
        include=include,
        exclude=exclude,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )
    if render:
        _render_report(reports, gap_summary)
    return gap_summary


def _analyse_model(model: type[Any], builder: StrategyBuilder) -> ModelReport:
    total_fields = 0
    covered_fields = 0
    issues: list[str] = []
    field_gaps: list[FieldGap] = []
    field_reports: list[FieldReport] = []

    summaries = summarize_model_fields(model)

    model_fields = getattr(model, "model_fields", None)

    for field_name, summary in summaries.items():
        total_fields += 1
        field_info = None
        annotation = summary.annotation
        if isinstance(model_fields, Mapping):
            model_field = model_fields.get(field_name)
            if model_field is not None:
                field_info = model_field
                annotation = model_field.annotation
        try:
            strategy = builder.build_field_strategy(
                model,
                field_name,
                annotation,
                summary,
                field_info=field_info,
            )
        except ValueError as exc:
            message = str(exc)
            issues.append(f"{model.__name__}.{field_name}: [error] {message}")
            gap_info = GapInfo(
                type_name=summary.type,
                reason=message,
                remediation="Register a custom provider or configure an override for this field.",
                severity="error",
            )
            field_gaps.append(FieldGap(model=model, field=field_name, info=gap_info))
            field_reports.append(
                FieldReport(
                    name=field_name,
                    type_name=summary.type,
                    provider=None,
                    covered=False,
                    gaps=[gap_info],
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
        field_reports.append(
            FieldReport(
                name=field_name,
                type_name=summary.type,
                provider=_strategy_provider_label(strategy),
                covered=covered,
                gaps=list(gap_infos),
            )
        )

    return ModelReport(
        model=model,
        coverage=(covered_fields, total_fields),
        issues=issues,
        gaps=field_gaps,
        fields=field_reports,
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


def _strategy_provider_label(strategy: StrategyResult) -> str | None:
    if isinstance(strategy, UnionStrategy):
        return f"union:{strategy.policy}"
    if isinstance(strategy, Strategy):
        if strategy.provider_name:
            return strategy.provider_name
        if strategy.summary.type in {"model", "dataclass"}:
            return strategy.summary.type
    return None


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
        module_name = canonical_module_name(report.model)
        typer.echo(f"Model: {module_name}.{report.model.__name__}")
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


__all__ = ["app", "get_plugin_manager", "ModelReport", "FieldReport", "_run_doctor_analysis"]
