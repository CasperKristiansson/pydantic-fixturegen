"""Polyfactory-specific CLI helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.api._runtime import _build_instance_generator, _build_relation_model_map
from pydantic_fixturegen.cli.gen import _common as cli_common
from pydantic_fixturegen.cli.gen._common import JSON_ERRORS_OPTION, render_cli_error, split_patterns
from pydantic_fixturegen.core.config import load_config
from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.logging import Logger, get_logger
from pydantic_fixturegen.polyfactory_support.discovery import (
    POLYFACTORY_MODEL_FACTORY,
    POLYFACTORY_UNAVAILABLE_REASON,
    PolyfactoryBinding,
    discover_polyfactory_bindings,
)
from pydantic_fixturegen.polyfactory_support.migration import (
    FactoryReport,
    analyze_binding,
    merge_override_maps,
    render_overrides_toml,
    reports_to_jsonable,
)

TARGET_ARGUMENT = typer.Argument(..., help="Path to a Python module containing models.")
FORMAT_OPTION = typer.Option(
    "table",
    "--format",
    "-f",
    help="Output format: table or json.",
    case_sensitive=False,
)
INCLUDE_OPTION = typer.Option(None, "--include", "-i", help="Comma-separated include globs.")
EXCLUDE_OPTION = typer.Option(None, "--exclude", "-e", help="Comma-separated exclude globs.")
OVERRIDES_OPTION = typer.Option(
    None,
    "--overrides-out",
    help="Write translated overrides to a TOML file.",
)


app = typer.Typer(help="Polyfactory migration helpers.")


@app.command("migrate")
def migrate(  # noqa: PLR0913 - CLI surface mirrors documentation
    target: Path = TARGET_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    factory_module: str | None = typer.Option(
        None,
        "--factory-module",
        "-m",
        help="Comma-separated module(s) to scan for Polyfactory factories.",
    ),
    format: str = FORMAT_OPTION,
    overrides_out: Path | None = OVERRIDES_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    """Analyze Polyfactory factories and emit migration guidance."""

    logger = get_logger()

    if POLYFACTORY_MODEL_FACTORY is None:
        reason = POLYFACTORY_UNAVAILABLE_REASON or "Polyfactory is not installed."
        render_cli_error(DiscoveryError(reason), json_errors=json_errors)
        return

    if not target.exists():
        render_cli_error(
            DiscoveryError(f"Target path '{target}' does not exist."),
            json_errors=json_errors,
        )
        return

    app_config = load_config(root=Path.cwd())
    include_patterns = split_patterns(include)
    exclude_patterns = split_patterns(exclude)
    discovery = cli_common.discover_models(
        target,
        include=include_patterns or None,
        exclude=exclude_patterns or None,
    )
    if discovery.errors:
        render_cli_error(DiscoveryError("; ".join(discovery.errors)), json_errors=json_errors)
        return
    if not discovery.models:
        render_cli_error(DiscoveryError("No models discovered."), json_errors=json_errors)
        return

    try:
        model_lookup = {
            model.qualname: cli_common.load_model_class(model) for model in discovery.models
        }
    except RuntimeError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
        return
    model_classes = tuple(model_lookup.values())

    format = format.lower()
    if format not in {"table", "json"}:
        raise typer.BadParameter("format must be 'table' or 'json'.")

    extra_modules = list(app_config.polyfactory.modules)
    extra_modules.extend(split_patterns(factory_module) or [])

    discovery_modules = [model.module for model in discovery.models]
    log_target = None if format == "json" else logger
    bindings = _discover_bindings(
        model_classes,
        discovery_modules,
        extra_modules,
        log_target,
    )
    if not bindings:
        render_cli_error(
            DiscoveryError("No Polyfactory factories found for the selected models."),
            json_errors=json_errors,
        )
        return

    relation_map = _build_relation_model_map(model_classes)
    try:
        generator = _build_instance_generator(app_config, relation_models=relation_map)
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
        return

    reports = []
    for binding in bindings:
        strategies = generator._get_model_strategies(binding.model)  # pyright: ignore[reportPrivateUsage]
        reports.append(analyze_binding(binding, strategies=strategies))

    if format == "json":
        typer.echo(json.dumps(reports_to_jsonable(reports), indent=2))
    else:
        _render_table(reports)

    overrides = merge_override_maps(reports)
    if overrides_out:
        content = render_overrides_toml(overrides)
        overrides_out.parent.mkdir(parents=True, exist_ok=True)
        overrides_out.write_text(content, encoding="utf-8")
        if format != "json":
            logger.info(
                "Polyfactory overrides written",
                event="polyfactory_overrides_written",
                path=str(overrides_out),
                models=len(overrides),
            )


def _discover_bindings(
    models: Sequence[type[Any]],
    module_names: Sequence[str],
    extra_modules: Sequence[str],
    logger: Logger | None,
) -> list[PolyfactoryBinding]:
    return discover_polyfactory_bindings(
        model_classes=models,
        discovery_modules=module_names,
        extra_modules=extra_modules,
        logger=logger,
    )


def _render_table(reports: Sequence[FactoryReport]) -> None:
    for report in reports:
        typer.echo(f"Model: {report.model_label}")
        typer.echo(f"Factory: {report.factory_label}")
        for field in report.fields:
            status = "translated" if field.translated else "manual"
            typer.echo(f"  - {field.name} [{status}]")
            typer.echo(f"      Polyfactory: {field.detail}")
            if field.fixturegen_provider:
                typer.echo(f"      Fixturegen: {field.fixturegen_provider}")
            if field.translated and field.translation:
                typer.echo(f"      Override: {json.dumps(field.translation)}")
            if field.message:
                typer.echo(f"      Note: {field.message}")
        typer.echo("")


__all__ = ["app"]
