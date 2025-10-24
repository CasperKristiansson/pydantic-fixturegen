"""CLI command for emitting JSON schema files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.core.config import ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ._common import (
    JSON_ERRORS_OPTION,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

OUT_OPTION = typer.Option(
    ...,
    "--out",
    "-o",
    help="Output file path for the generated schema.",
)

INDENT_OPTION = typer.Option(
    None,
    "--indent",
    min=0,
    help="Indentation level for JSON output (overrides config).",
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


def register(app: typer.Typer) -> None:
    @app.command("schema")
    def gen_schema(  # noqa: PLR0913
        target: str = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        indent: int | None = INDENT_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
    ) -> None:
        try:
            _execute_schema_command(
                target=target,
                out=out,
                indent=indent,
                include=include,
                exclude=exclude,
            )
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
        except ConfigError as exc:
            render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
        except Exception as exc:  # pragma: no cover - defensive
            render_cli_error(EmitError(str(exc)), json_errors=json_errors)


def _execute_schema_command(
    *,
    target: str,
    out: Path,
    indent: int | None,
    include: str | None,
    exclude: str | None,
) -> None:
    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    clear_module_cache()
    load_entrypoint_plugins()

    cli_overrides: dict[str, Any] = {}
    if indent is not None:
        cli_overrides.setdefault("json", {})["indent"] = indent
    if include:
        cli_overrides["include"] = split_patterns(include)
    if exclude:
        cli_overrides["exclude"] = split_patterns(exclude)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)

    discovery = discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            typer.secho(warning.strip(), err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    try:
        model_classes = [load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:
        raise DiscoveryError(str(exc)) from exc

    indent_value = indent if indent is not None else app_config.json.indent

    context = EmitterContext(
        models=tuple(model_classes),
        output=out,
        parameters={"indent": indent_value},
    )
    if emit_artifact("schema", context):
        return

    try:
        if len(model_classes) == 1:
            emitted_path = emit_model_schema(
                model_classes[0],
                output_path=out,
                indent=indent_value,
                ensure_ascii=False,
            )
        else:
            emitted_path = emit_models_schema(
                model_classes,
                output_path=out,
                indent=indent_value,
                ensure_ascii=False,
            )
    except Exception as exc:
        raise EmitError(str(exc)) from exc

    typer.echo(str(emitted_path))


__all__ = ["register"]
