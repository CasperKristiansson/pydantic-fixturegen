"""Model coverage reporting CLI."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import typer

from pydantic_fixturegen.core.config import RelationLinkConfig, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.overrides import FieldOverrideSet, build_field_override_set
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldSummary, summarize_model_fields
from pydantic_fixturegen.core.seed_freeze import canonical_module_name
from pydantic_fixturegen.core.strategies import (
    Strategy,
    StrategyBuilder,
    StrategyResult,
    UnionStrategy,
)
from pydantic_fixturegen.plugins.loader import get_plugin_manager

from .doctor import _strategy_provider_label, _strategy_status
from .gen import _common as cli_common
from .gen._common import render_cli_error

PATH_ARGUMENT = typer.Argument(
    None,
    help="Path to a Python module containing supported models (Pydantic, dataclass, TypedDict).",
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

FORMAT_OPTION = typer.Option(
    "text",
    "--format",
    case_sensitive=False,
    help="Output format: text or json.",
)

FAIL_ON_OPTION = typer.Option(
    "none",
    "--fail-on",
    case_sensitive=False,
    help=(
        "Fail with exit code 2 when risks are detected "
        "(none, heuristics, relations, overrides, any)."
    ),
)


app = typer.Typer(help="Model coverage dashboards (heuristics, overrides, relations)")


@dataclass(slots=True)
class CoverageModel:
    model: type[Any]
    covered_fields: int
    total_fields: int
    provider_counts: Counter[str]
    heuristic_fields: list[str] = field(default_factory=list)
    override_fields: list[str] = field(default_factory=list)
    uncovered_fields: list[str] = field(default_factory=list)

    def coverage_percent(self) -> float:
        if not self.total_fields:
            return 100.0
        return (self.covered_fields / self.total_fields) * 100

    @property
    def display_name(self) -> str:
        return _model_label(self.model)

    def to_payload(self) -> dict[str, Any]:
        provider_data = dict(
            sorted(self.provider_counts.items(), key=lambda item: (-item[1], item[0]))
        )
        return {
            "name": self.display_name,
            "coverage": {
                "covered": self.covered_fields,
                "total": self.total_fields,
                "percent": round(self.coverage_percent(), 2),
            },
            "provider_counts": provider_data,
            "heuristic_fields": list(self.heuristic_fields),
            "override_fields": list(self.override_fields),
            "uncovered_fields": list(self.uncovered_fields),
        }


@dataclass(slots=True)
class CoverageTotals:
    total_models: int
    total_fields: int
    covered_fields: int
    heuristic_fields: int
    override_matches: int
    uncovered_fields: int

    def coverage_percent(self) -> float:
        if not self.total_fields:
            return 100.0
        return (self.covered_fields / self.total_fields) * 100

    def to_payload(self) -> dict[str, Any]:
        return {
            "models": self.total_models,
            "fields": self.total_fields,
            "covered_fields": self.covered_fields,
            "coverage_percent": round(self.coverage_percent(), 2),
            "heuristic_fields": self.heuristic_fields,
            "override_matches": self.override_matches,
            "uncovered_fields": self.uncovered_fields,
        }


@dataclass(slots=True)
class CoverageReport:
    models: list[CoverageModel]
    totals: CoverageTotals
    heuristic_details: list[dict[str, str]]
    unused_overrides: list[dict[str, str]]
    relation_issues: list[dict[str, str]]

    def has_heuristics(self) -> bool:
        return bool(self.heuristic_details)

    def has_unused_overrides(self) -> bool:
        return bool(self.unused_overrides)

    def has_relation_issues(self) -> bool:
        return bool(self.relation_issues)

    def to_payload(self) -> dict[str, Any]:
        return {
            "models": [model.to_payload() for model in self.models],
            "summary": self.totals.to_payload(),
            "heuristic_fields": list(self.heuristic_details),
            "unused_overrides": list(self.unused_overrides),
            "relation_issues": list(self.relation_issues),
        }


class CoverageOverrideTracker:
    def __init__(self, override_set: FieldOverrideSet | None) -> None:
        self._set = override_set
        self._usage: dict[int, list[str]] = {}
        self._descriptors = tuple(override_set.describe()) if override_set is not None else ()
        for descriptor in self._descriptors:
            self._usage[id(descriptor.override)] = []

    def resolve(self, model_cls: type[Any], field_name: str, field_info: Any) -> bool:
        if self._set is None:
            return False
        model_keys = _model_identifier_keys(model_cls)
        alias = _field_alias(field_info, field_name)
        aliases = (alias,) if alias else None
        override = self._set.resolve(model_keys=model_keys, field_name=field_name, aliases=aliases)
        if override is None:
            return False
        label = f"{_model_label(model_cls)}.{field_name}"
        self._usage.setdefault(id(override), []).append(label)
        return True

    def unused(self) -> list[dict[str, str]]:
        unused_items: list[dict[str, str]] = []
        for descriptor in self._descriptors:
            matches = self._usage.get(id(descriptor.override), [])
            if matches:
                continue
            unused_items.append(
                {
                    "model_pattern": descriptor.model_pattern,
                    "field_pattern": descriptor.field_pattern,
                }
            )
        return unused_items


@app.command()
def report(  # noqa: D401 - CLI entrypoint
    path: str | None = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    output_format: str = FORMAT_OPTION,
    fail_on: str = FAIL_ON_OPTION,
) -> None:
    try:
        report = _generate_coverage_report(
            target=path,
            include=include,
            exclude=exclude,
            ast_mode=ast_mode,
            hybrid_mode=hybrid_mode,
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=output_format.lower() == "json")
        return

    fmt = output_format.lower()
    if fmt not in {"text", "json"}:
        typer.secho(f"Unsupported format: {output_format}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    if fmt == "json":
        typer.echo(json.dumps(report.to_payload(), indent=2))
    else:
        _render_text_report(report)

    if _should_fail(report, fail_on.lower()):
        raise typer.Exit(code=2)


def _generate_coverage_report(
    *,
    target: str | None,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
) -> CoverageReport:
    if target is None:
        raise DiscoveryError("Provide a module path to analyse.")

    module_path = Path(target)

    cli_common.clear_module_cache()

    method = _resolve_method(ast_mode, hybrid_mode)
    discovery = cli_common.discover_models(
        module_path,
        include=cli_common.split_patterns(include),
        exclude=cli_common.split_patterns(exclude),
        method=method,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        text = warning.strip()
        if text:
            typer.secho(f"warning: {text}", err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        return CoverageReport(
            models=[],
            totals=CoverageTotals(0, 0, 0, 0, 0, 0),
            heuristic_details=[],
            unused_overrides=[],
            relation_issues=[],
        )

    app_config = load_config(root=Path.cwd())

    registry = create_default_registry(load_plugins=True)
    builder = StrategyBuilder(
        registry,
        plugin_manager=get_plugin_manager(),
        heuristics_enabled=app_config.heuristics.enabled,
        provider_defaults=app_config.provider_defaults,
        cycle_policy=app_config.cycle_policy,
    )

    override_set = build_field_override_set(app_config.overrides)
    override_tracker = CoverageOverrideTracker(override_set)

    model_reports: list[CoverageModel] = []
    heuristic_details: list[dict[str, str]] = []
    summaries_by_model: dict[type[Any], Mapping[str, FieldSummary]] = {}

    for model_info in discovery.models:
        try:
            model_cls = cli_common.load_model_class(model_info)
        except RuntimeError as exc:
            raise DiscoveryError(str(exc)) from exc

        summaries = summarize_model_fields(model_cls)
        summaries_by_model[model_cls] = summaries
        model_report, field_risks = _analyse_model(
            model_cls=model_cls,
            builder=builder,
            summaries=summaries,
            override_tracker=override_tracker,
        )
        model_reports.append(model_report)
        heuristic_details.extend(field_risks)

    relation_issues = _validate_relations(app_config.relations, model_reports, summaries_by_model)
    unused_overrides = override_tracker.unused()

    totals = _summarize_totals(model_reports)

    return CoverageReport(
        models=model_reports,
        totals=totals,
        heuristic_details=heuristic_details,
        unused_overrides=unused_overrides,
        relation_issues=relation_issues,
    )


def _analyse_model(
    *,
    model_cls: type[Any],
    builder: StrategyBuilder,
    summaries: Mapping[str, FieldSummary],
    override_tracker: CoverageOverrideTracker,
) -> tuple[CoverageModel, list[dict[str, str]]]:
    heuristics: list[str] = []
    overrides: list[str] = []
    uncovered: list[str] = []
    provider_counts: Counter[str] = Counter()
    heuristic_details: list[dict[str, str]] = []
    covered_fields = 0

    model_fields = getattr(model_cls, "model_fields", None)
    model_label = _model_label(model_cls)

    for field_name, summary in summaries.items():
        annotation = summary.annotation
        field_info = None
        if isinstance(model_fields, Mapping):
            model_field = model_fields.get(field_name)
            if model_field is not None:
                field_info = model_field
                annotation = model_field.annotation

        strategy = builder.build_field_strategy(
            model_cls,
            field_name,
            annotation,
            summary,
            field_info=field_info,
        )

        covered, _ = _strategy_status(summary, strategy)
        if covered:
            covered_fields += 1
        else:
            uncovered.append(field_name)

        provider_label = _strategy_provider_label(strategy) or "<unassigned>"
        provider_counts[provider_label] += 1

        if _strategy_has_heuristic(strategy):
            heuristics.append(field_name)
            heuristic_details.append(
                {
                    "model": model_label,
                    "field": field_name,
                    "provider": provider_label,
                }
            )

        if override_tracker.resolve(model_cls, field_name, field_info):
            overrides.append(field_name)

    model_report = CoverageModel(
        model=model_cls,
        covered_fields=covered_fields,
        total_fields=len(summaries),
        provider_counts=provider_counts,
        heuristic_fields=heuristics,
        override_fields=overrides,
        uncovered_fields=uncovered,
    )
    return model_report, heuristic_details


def _summarize_totals(models: list[CoverageModel]) -> CoverageTotals:
    total_models = len(models)
    total_fields = sum(model.total_fields for model in models)
    covered_fields = sum(model.covered_fields for model in models)
    heuristic_fields = sum(len(model.heuristic_fields) for model in models)
    override_matches = sum(len(model.override_fields) for model in models)
    uncovered_fields = sum(len(model.uncovered_fields) for model in models)
    return CoverageTotals(
        total_models=total_models,
        total_fields=total_fields,
        covered_fields=covered_fields,
        heuristic_fields=heuristic_fields,
        override_matches=override_matches,
        uncovered_fields=uncovered_fields,
    )


def _validate_relations(
    relations: tuple[RelationLinkConfig, ...],
    models: list[CoverageModel],
    summaries: Mapping[type[Any], Mapping[str, FieldSummary]],
) -> list[dict[str, str]]:
    if not relations:
        return []

    lookup = _build_model_lookup(models)
    issues: list[dict[str, str]] = []

    for link in relations:
        source_model, source_field = _split_endpoint(link.source)
        target_model, target_field = _split_endpoint(link.target)

        src_cls = lookup.get(source_model)
        if src_cls is None:
            issues.append(
                {
                    "relation": link.source,
                    "target": link.target,
                    "reason": f"source model '{source_model}' not found",
                }
            )
            continue
        target_cls = lookup.get(target_model)
        if target_cls is None:
            issues.append(
                {
                    "relation": link.source,
                    "target": link.target,
                    "reason": f"target model '{target_model}' not found",
                }
            )
            continue

        src_summary = summaries.get(src_cls)
        tgt_summary = summaries.get(target_cls)
        if src_summary is None or source_field not in src_summary:
            issues.append(
                {
                    "relation": link.source,
                    "target": link.target,
                    "reason": f"source field '{source_field}' not found",
                }
            )
            continue
        if tgt_summary is None or target_field not in tgt_summary:
            issues.append(
                {
                    "relation": link.source,
                    "target": link.target,
                    "reason": f"target field '{target_field}' not found",
                }
            )
    return issues


def _render_text_report(report: CoverageReport) -> None:
    if not report.models:
        typer.echo("No models discovered.")
        return

    for model in report.models:
        typer.echo(f"Model: {model.display_name}")
        coverage_percent = model.coverage_percent()
        typer.echo(
            "  Coverage: "
            f"{model.covered_fields}/{model.total_fields} fields ("
            f"{coverage_percent:.0f}%)"
        )
        if model.provider_counts:
            typer.echo("  Providers:")
            for provider, count in sorted(
                model.provider_counts.items(), key=lambda item: (-item[1], item[0])
            ):
                typer.echo(f"    - {provider}: {count}")
        _render_list("  Heuristic fields", model.heuristic_fields)
        _render_list("  Override matches", model.override_fields)
        _render_list("  Uncovered fields", model.uncovered_fields)
        typer.echo("")

    typer.echo("Summary:")
    typer.echo(f"  Models: {report.totals.total_models}")
    typer.echo(
        f"  Fields: {report.totals.total_fields} (covered={report.totals.covered_fields},"
        f" {report.totals.coverage_percent():.0f}% deterministic)"
    )
    typer.echo(f"  Heuristic fields: {report.totals.heuristic_fields}")
    typer.echo(f"  Override matches: {report.totals.override_matches}")
    typer.echo(f"  Uncovered fields: {report.totals.uncovered_fields}")
    typer.echo(f"  Unused overrides: {len(report.unused_overrides)}")
    typer.echo(f"  Relation issues: {len(report.relation_issues)}")

    if report.heuristic_details:
        typer.echo("\nHeuristic-only fields:")
        for detail in report.heuristic_details:
            provider = detail.get("provider") or "<unassigned>"
            typer.echo(f"  - {detail['model']}.{detail['field']} (provider={provider})")

    if report.unused_overrides:
        typer.echo("\nUnused overrides:")
        for entry in report.unused_overrides:
            typer.echo(
                f"  - model={entry['model_pattern']} field={entry['field_pattern']} (no matches)"
            )

    if report.relation_issues:
        typer.echo("\nRelation issues:")
        for issue in report.relation_issues:
            typer.echo(f"  - {issue['relation']} -> {issue['target']}: {issue['reason']}")


def _render_list(label: str, values: list[str]) -> None:
    if values:
        typer.echo(f"{label}: {', '.join(sorted(values))}")
    else:
        typer.echo(f"{label}: none")


def _should_fail(report: CoverageReport, fail_on: str) -> bool:
    if fail_on == "none":
        return False
    if fail_on == "heuristics":
        return report.has_heuristics()
    if fail_on == "relations":
        return report.has_relation_issues()
    if fail_on == "overrides":
        return report.has_unused_overrides()
    if fail_on == "any":
        return any(
            (
                report.has_heuristics(),
                report.has_relation_issues(),
                report.has_unused_overrides(),
            )
        )
    typer.secho(f"Unknown fail-on option: {fail_on}", err=True, fg=typer.colors.RED)
    return True


def _strategy_has_heuristic(strategy: StrategyResult) -> bool:
    if isinstance(strategy, UnionStrategy):
        return any(_strategy_has_heuristic(choice) for choice in strategy.choices)
    if isinstance(strategy, Strategy):
        return strategy.heuristic is not None
    return False


def _model_identifier_keys(model_cls: type[Any]) -> tuple[str, ...]:
    full = _model_label(model_cls)
    qualname = getattr(model_cls, "__qualname__", "")
    name = getattr(model_cls, "__name__", "")
    simple = qualname.split(".")[-1] if qualname else name
    keys: list[str] = []
    for candidate in (full, qualname, name, simple):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return tuple(keys)


def _field_alias(field_info: Any, field_name: str) -> str | None:
    alias = getattr(field_info, "alias", None) if field_info is not None else None
    if isinstance(alias, str) and alias != field_name:
        return alias
    return None


def _build_model_lookup(models: list[CoverageModel]) -> dict[str, type[Any]]:
    lookup: dict[str, type[Any]] = {}
    for model in models:
        for key in _model_identifier_keys(model.model):
            lookup.setdefault(key, model.model)
    return lookup


def _model_label(model_cls: type[Any]) -> str:
    module = canonical_module_name(model_cls)
    qualname = getattr(model_cls, "__qualname__", getattr(model_cls, "__name__", "<unknown>"))
    return f"{module}.{qualname}" if module else qualname


def _split_endpoint(endpoint: str) -> tuple[str, str]:
    text = endpoint.strip()
    if not text or "." not in text:
        raise DiscoveryError("Relation endpoints must look like 'Model.field'.")
    model, field = text.rsplit(".", 1)
    return model.strip(), field.strip()


def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> Literal["ast", "import", "hybrid"]:
    if ast_mode and hybrid_mode:
        raise DiscoveryError("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


__all__ = ["app"]
