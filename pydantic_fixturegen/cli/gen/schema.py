"""CLI command for emitting JSON schema files."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.core.config import ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ...logging import get_logger
from ..watch import gather_default_watch_paths, run_with_watch
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

WATCH_OPTION = typer.Option(
    False,
    "--watch",
    help="Watch source files and regenerate when changes are detected.",
)

WATCH_DEBOUNCE_OPTION = typer.Option(
    0.5,
    "--watch-debounce",
    min=0.1,
    help="Debounce interval in seconds for filesystem events.",
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
        watch: bool = WATCH_OPTION,
        watch_debounce: float = WATCH_DEBOUNCE_OPTION,
    ) -> None:
        logger = get_logger()

        try:
            output_template = OutputTemplate(str(out))
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
            return

        watch_output: Path | None = None
        watch_extra: list[Path] | None = None
        if output_template.has_dynamic_directories():
            watch_extra = [output_template.watch_parent()]
        else:
            watch_output = output_template.preview_path()

        def invoke(exit_app: bool) -> None:
            try:
                _execute_schema_command(
                    target=target,
                    output_template=output_template,
                    indent=indent,
                    include=include,
                    exclude=exclude,
                )
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors, exit_app=exit_app)
            except ConfigError as exc:
                render_cli_error(
                    DiscoveryError(str(exc)),
                    json_errors=json_errors,
                    exit_app=exit_app,
                )
            except Exception as exc:  # pragma: no cover - defensive
                render_cli_error(
                    EmitError(str(exc)),
                    json_errors=json_errors,
                    exit_app=exit_app,
                )

        if watch:
            watch_paths = gather_default_watch_paths(
                Path(target),
                output=watch_output,
                extra=watch_extra,
            )
            try:
                logger.debug(
                    "Entering watch loop",
                    event="watch_loop_enter",
                    target=str(target),
                    output=str(watch_output or output_template.preview_path()),
                    debounce=watch_debounce,
                )
                run_with_watch(lambda: invoke(exit_app=False), watch_paths, debounce=watch_debounce)
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
        else:
            invoke(exit_app=True)


def _execute_schema_command(
    *,
    target: str,
    output_template: OutputTemplate,
    indent: int | None,
    include: str | None,
    exclude: str | None,
) -> None:
    logger = get_logger()
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

    logger.debug(
        "Loaded configuration",
        event="config_loaded",
        indent=indent,
        include=list(app_config.include),
        exclude=list(app_config.exclude),
    )

    discovery = discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            logger.warn(
                warning.strip(),
                event="discovery_warning",
                warning=warning.strip(),
            )

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    try:
        model_classes = [load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:
        raise DiscoveryError(str(exc)) from exc

    indent_value = indent if indent is not None else app_config.json.indent

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    if len(model_classes) == 1:
        template_context = OutputTemplateContext(
            model=model_classes[0].__name__,
            timestamp=timestamp,
        )
    else:
        if "model" in output_template.fields:
            names = ", ".join(cls.__name__ for cls in model_classes)
            raise EmitError(
                "Template variable '{model}' requires a single model selection.",
                details={"models": names},
            )
        template_context = OutputTemplateContext(timestamp=timestamp)

    resolved_output = output_template.render(
        context=template_context,
        case_index=1 if output_template.uses_case_index() else None,
    )

    context = EmitterContext(
        models=tuple(model_classes),
        output=resolved_output,
        parameters={"indent": indent_value, "path_template": output_template.raw},
    )
    if emit_artifact("schema", context):
        logger.info(
            "Schema generation handled by plugin",
            event="schema_generation_delegated",
            output=str(resolved_output),
        )
        return

    try:
        if len(model_classes) == 1:
            emitted_path = emit_model_schema(
                model_classes[0],
                output_path=output_template.raw,
                indent=indent_value,
                ensure_ascii=False,
                template=output_template,
                template_context=template_context,
            )
        else:
            emitted_path = emit_models_schema(
                model_classes,
                output_path=output_template.raw,
                indent=indent_value,
                ensure_ascii=False,
                template=output_template,
                template_context=template_context,
            )
    except Exception as exc:
        raise EmitError(str(exc)) from exc

    logger.info(
        "Schema generation complete",
        event="schema_generation_complete",
        output=str(emitted_path),
        models=[model.__name__ for model in model_classes],
    )
    typer.echo(str(emitted_path))


__all__ = ["register"]
