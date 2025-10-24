"""CLI command to explain strategies for models and fields."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import summarize_model_fields
from pydantic_fixturegen.core.strategies import StrategyBuilder, StrategyResult, UnionStrategy

from ._common import (
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


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")


def explain(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        _execute_explain(
            target=path,
            include=include,
            exclude=exclude,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
    except ValueError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)


app.callback(invoke_without_command=True)(explain)


def _execute_explain(*, target: str, include: str | None, exclude: str | None) -> None:
    path = Path(target)
    if not path.exists():
        raise ValueError(f"Target path '{target}' does not exist.")
    if not path.is_file():
        raise ValueError("Target must be a Python module file.")

    clear_module_cache()

    discovery = discover_models(
        path,
        include=split_patterns(include),
        exclude=split_patterns(exclude),
    )

    if discovery.errors:
        raise ValueError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            typer.secho(f"warning: {warning.strip()}", err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        typer.echo("No models discovered.")
        return

    registry = create_default_registry(load_plugins=True)
    builder = StrategyBuilder(registry)

    for model_info in discovery.models:
        model_cls = load_model_class(model_info)
        _render_model_report(model_cls, builder)


def _render_model_report(model: type[BaseModel], builder: StrategyBuilder) -> None:
    typer.echo(f"Model: {model.__module__}.{model.__name__}")
    summaries = summarize_model_fields(model)
    strategies = {}
    field_failures: dict[str, str] = {}
    for name, model_field in model.model_fields.items():
        summary = summaries[name]
        try:
            strategies[name] = builder.build_field_strategy(
                model,
                name,
                model_field.annotation,
                summary,
            )
        except ValueError as exc:
            field_failures[name] = str(exc)

    for field_name, strategy in strategies.items():
        summary = summaries[field_name]
        typer.echo(f"  Field: {field_name}")
        typer.echo(f"    Type: {summary.type}")
        _render_strategy(strategy, indent="    ")
    for field_name, message in field_failures.items():
        typer.echo(f"  Field: {field_name}")
        typer.echo("    Type: unknown")
        typer.echo(f"    Issue: {message}")
    typer.echo("")


def _render_strategy(strategy: StrategyResult, indent: str) -> None:
    if isinstance(strategy, UnionStrategy):
        typer.echo(f"{indent}Union policy: {strategy.policy}")
        for idx, choice in enumerate(strategy.choices, start=1):
            typer.echo(f"{indent}  Option {idx} -> type: {choice.summary.type}")
            _render_strategy(choice, indent=f"{indent}    ")
        return

    typer.echo(f"{indent}Provider: {strategy.provider_name}")
    if strategy.enum_values:
        typer.echo(f"{indent}Enum values: {strategy.enum_values}")
    typer.echo(f"{indent}p_none: {strategy.p_none}")


__all__ = ["app"]
