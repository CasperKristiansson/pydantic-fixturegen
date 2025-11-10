"""CLI command for emitting JSON schema files."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen._warnings import apply_warning_filters
from pydantic_fixturegen.api._runtime import generate_schema_artifacts
from pydantic_fixturegen.api.models import SchemaGenerationResult
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate

from ...logging import Logger, get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from ._common import JSON_ERRORS_OPTION, render_cli_error

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

PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Apply a privacy profile before schema generation (e.g. 'pii-safe').",
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
        profile: str | None = PROFILE_OPTION,
    ) -> None:
        apply_warning_filters()
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
                    profile=profile,
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
    profile: str | None = None,
) -> None:
    logger = get_logger()

    include_patterns = [include] if include else None
    exclude_patterns = [exclude] if exclude else None

    try:
        result = generate_schema_artifacts(
            target=target,
            output_template=output_template,
            indent=indent,
            include=include_patterns,
            exclude=exclude_patterns,
            profile=profile,
            logger=logger,
        )
    except PFGError as exc:
        _handle_schema_error(logger, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if isinstance(exc, ConfigError):
            raise
        raise EmitError(str(exc)) from exc

    if _log_schema_snapshot(logger, result):
        return

    typer.echo(str(result.path))


def _log_schema_snapshot(logger: Logger, result: SchemaGenerationResult) -> bool:
    config_snapshot = result.config
    anchor_iso = config_snapshot.time_anchor.isoformat() if config_snapshot.time_anchor else None

    logger.debug(
        "Loaded configuration",
        event="config_loaded",
        include=list(config_snapshot.include),
        exclude=list(config_snapshot.exclude),
        time_anchor=anchor_iso,
    )

    if anchor_iso:
        logger.info(
            "Using temporal anchor",
            event="temporal_anchor_set",
            time_anchor=anchor_iso,
        )

    for warning in result.warnings:
        logger.warn(
            warning,
            event="discovery_warning",
            warning=warning,
        )

    if result.delegated:
        logger.info(
            "Schema generation handled by plugin",
            event="schema_generation_delegated",
            output=str(result.base_output),
            time_anchor=anchor_iso,
        )
        return True

    logger.info(
        "Schema generation complete",
        event="schema_generation_complete",
        output=str(result.path),
        models=[model.__name__ for model in result.models],
        time_anchor=anchor_iso,
    )
    return False


def _handle_schema_error(logger: Logger, exc: PFGError) -> None:
    details = getattr(exc, "details", {}) or {}
    config_info = details.get("config")
    anchor_iso = None
    if isinstance(config_info, dict):
        anchor_iso = config_info.get("time_anchor")
        logger.debug(
            "Loaded configuration",
            event="config_loaded",
            include=config_info.get("include", []),
            exclude=config_info.get("exclude", []),
            time_anchor=anchor_iso,
        )
        if anchor_iso:
            logger.info(
                "Using temporal anchor",
                event="temporal_anchor_set",
                time_anchor=anchor_iso,
            )

    warnings = details.get("warnings") or []
    for warning in warnings:
        if isinstance(warning, str):
            logger.warn(
                warning,
                event="discovery_warning",
                warning=warning,
            )


__all__ = ["register"]
