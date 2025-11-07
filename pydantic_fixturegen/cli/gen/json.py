"""CLI command for generating JSON/JSONL samples."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.api._runtime import generate_json_artifacts
from pydantic_fixturegen.api.models import JsonGenerationResult
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate

from ...logging import Logger, get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from ._common import JSON_ERRORS_OPTION, NOW_OPTION, emit_constraint_summary, render_cli_error

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

OUT_OPTION = typer.Option(
    ...,
    "--out",
    "-o",
    help="Output file path (single file or shard prefix).",
)

COUNT_OPTION = typer.Option(
    1,
    "--n",
    "-n",
    min=1,
    help="Number of samples to generate.",
)

JSONL_OPTION = typer.Option(
    False,
    "--jsonl",
    help="Emit newline-delimited JSON instead of a JSON array.",
)

INDENT_OPTION = typer.Option(
    None,
    "--indent",
    min=0,
    help="Indentation level for JSON output (overrides config).",
)

ORJSON_OPTION = typer.Option(
    None,
    "--orjson/--no-orjson",
    help="Toggle orjson serialization (overrides config).",
)

SHARD_OPTION = typer.Option(
    None,
    "--shard-size",
    min=1,
    help="Maximum number of records per shard (JSONL or JSON).",
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

SEED_OPTION = typer.Option(
    None,
    "--seed",
    help="Seed override for deterministic generation.",
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

FREEZE_SEEDS_OPTION = typer.Option(
    False,
    "--freeze-seeds/--no-freeze-seeds",
    help="Read/write per-model seeds using a freeze file to ensure deterministic regeneration.",
)

FREEZE_FILE_OPTION = typer.Option(
    None,
    "--freeze-seeds-file",
    help="Seed freeze file path (defaults to `.pfg-seeds.json` in the project root).",
)

PRESET_OPTION = typer.Option(
    None,
    "--preset",
    help="Apply a curated generation preset (e.g. 'boundary', 'boundary-max').",
)

PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Apply a privacy profile (e.g. 'pii-safe', 'realistic').",
)


def register(app: typer.Typer) -> None:
    @app.command("json")
    def gen_json(  # noqa: PLR0913 - CLI surface mirrors documented parameters
        target: str = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        count: int = COUNT_OPTION,
        jsonl: bool = JSONL_OPTION,
        indent: int | None = INDENT_OPTION,
        use_orjson: bool | None = ORJSON_OPTION,
        shard_size: int | None = SHARD_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
        seed: int | None = SEED_OPTION,
        now: str | None = NOW_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
        watch: bool = WATCH_OPTION,
        watch_debounce: float = WATCH_DEBOUNCE_OPTION,
        freeze_seeds: bool = FREEZE_SEEDS_OPTION,
        freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
        preset: str | None = PRESET_OPTION,
        profile: str | None = PROFILE_OPTION,
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
                _execute_json_command(
                    target=target,
                    output_template=output_template,
                    count=count,
                    jsonl=jsonl,
                    indent=indent,
                    use_orjson=use_orjson,
                    shard_size=shard_size,
                    include=include,
                    exclude=exclude,
                    seed=seed,
                    freeze_seeds=freeze_seeds,
                    freeze_seeds_file=freeze_seeds_file,
                    preset=preset,
                    profile=profile,
                    now=now,
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


def _execute_json_command(
    *,
    target: str,
    output_template: OutputTemplate,
    count: int,
    jsonl: bool,
    indent: int | None,
    use_orjson: bool | None,
    shard_size: int | None,
    include: str | None,
    exclude: str | None,
    seed: int | None,
    now: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None = None,
) -> None:
    logger = get_logger()

    include_patterns = [include] if include else None
    exclude_patterns = [exclude] if exclude else None

    try:
        result = generate_json_artifacts(
            target=target,
            output_template=output_template,
            count=count,
            jsonl=jsonl,
            indent=indent,
            use_orjson=use_orjson,
            shard_size=shard_size,
            include=include_patterns,
            exclude=exclude_patterns,
            seed=seed,
            now=now,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_seeds_file,
            preset=preset,
            profile=profile,
            logger=logger,
        )
    except PFGError as exc:
        _handle_generation_error(logger, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if isinstance(exc, ConfigError):
            raise
        raise EmitError(str(exc)) from exc

    if _log_generation_snapshot(logger, result, count):
        return

    emit_constraint_summary(
        result.constraint_summary,
        logger=logger,
        json_mode=logger.config.json,
    )

    for emitted_path in result.paths:
        typer.echo(str(emitted_path))


def _log_generation_snapshot(logger: Logger, result: JsonGenerationResult, count: int) -> bool:
    config_snapshot = result.config
    anchor_iso = config_snapshot.time_anchor.isoformat() if config_snapshot.time_anchor else None

    logger.debug(
        "Loaded configuration",
        event="config_loaded",
        seed=config_snapshot.seed,
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
            "JSON generation handled by plugin",
            event="json_generation_delegated",
            output=str(result.base_output),
            time_anchor=anchor_iso,
        )
        return True

    logger.info(
        "JSON generation complete",
        event="json_generation_complete",
        files=[str(path) for path in result.paths],
        count=count,
        time_anchor=anchor_iso,
    )
    return False


def _handle_generation_error(logger: Logger, exc: PFGError) -> None:
    details = getattr(exc, "details", {}) or {}
    config_info = details.get("config")
    anchor_iso = None
    if isinstance(config_info, dict):
        anchor_iso = config_info.get("time_anchor")
        logger.debug(
            "Loaded configuration",
            event="config_loaded",
            seed=config_info.get("seed"),
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

    constraint_summary = details.get("constraint_summary")
    if constraint_summary:
        emit_constraint_summary(
            constraint_summary,
            logger=logger,
            json_mode=logger.config.json,
        )


__all__ = ["register"]
