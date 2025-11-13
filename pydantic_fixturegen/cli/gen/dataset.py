"""CLI command for generating CSV/Parquet/Arrow datasets."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.api._runtime import generate_dataset_artifacts
from pydantic_fixturegen.api.models import DatasetGenerationResult
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.core.schema_ingest import SchemaIngester

from ...logging import Logger, get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from . import _common as cli_common
from ._common import (
    JSON_ERRORS_OPTION,
    NOW_OPTION,
    RNG_MODE_OPTION,
    emit_constraint_summary,
    render_cli_error,
)

TARGET_ARGUMENT = typer.Argument(
    None,
    help="Path to a Python module containing Pydantic models (optional when using --schema).",
)

OUT_OPTION = typer.Option(
    ...,
    "--out",
    "-o",
    help="Output file path or template.",
)

COUNT_OPTION = typer.Option(
    1,
    "--n",
    "-n",
    min=1,
    help="Number of records to emit.",
)

FORMAT_OPTION = typer.Option(
    "csv",
    "--format",
    "-f",
    help="Dataset format: csv, parquet, or arrow.",
)

COMPRESSION_OPTION = typer.Option(
    None,
    "--compression",
    help="Compression codec (csv: gzip; parquet: snappy/gzip/brotli/zstd/lz4; arrow: zstd/lz4).",
)

SHARD_OPTION = typer.Option(
    None,
    "--shard-size",
    min=1,
    help="Maximum number of records per shard/file.",
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
    help="Debounce interval (seconds) for watch mode.",
)

FREEZE_SEEDS_OPTION = typer.Option(
    False,
    "--freeze-seeds/--no-freeze-seeds",
    help="Read/write per-model seeds via a freeze file.",
)

FREEZE_FILE_OPTION = typer.Option(
    None,
    "--freeze-seeds-file",
    help="Seed freeze file path (defaults to `.pfg-seeds.json`).",
)

PRESET_OPTION = typer.Option(
    None,
    "--preset",
    help="Apply a curated generation preset (e.g. 'boundary').",
)

PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Apply a privacy profile (e.g. 'pii-safe').",
)

RESPECT_VALIDATORS_OPTION = typer.Option(
    None,
    "--respect-validators/--no-respect-validators",
    help="Retry generation to satisfy validators before emitting samples.",
)

VALIDATOR_MAX_RETRIES_OPTION = typer.Option(
    None,
    "--validator-max-retries",
    min=0,
    help="Maximum additional validator retries when --respect-validators is enabled.",
)

LINK_OPTION = typer.Option(
    None,
    "--link",
    help="Declare relation link as source.field=target.field (repeatable).",
)

MAX_DEPTH_OPTION = typer.Option(
    None,
    "--max-depth",
    min=1,
    help="Override the maximum recursion depth for nested models.",
)

CYCLE_POLICY_OPTION = typer.Option(
    None,
    "--on-cycle",
    help="Cycle handling policy when recursion occurs (reuse, stub, or null).",
)

SCHEMA_OPTION = typer.Option(
    None,
    "--schema",
    help="Path to a JSON Schema document to ingest before generation.",
)


def register(app: typer.Typer) -> None:
    @app.command("dataset")
    def gen_dataset(  # noqa: PLR0913 - CLI mirrors documentation
        target: str | None = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        count: int = COUNT_OPTION,
        dataset_format: str = FORMAT_OPTION,
        compression: str | None = COMPRESSION_OPTION,
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
        respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
        validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
        links: list[str] | None = LINK_OPTION,
        max_depth: int | None = MAX_DEPTH_OPTION,
        cycle_policy: str | None = CYCLE_POLICY_OPTION,
        rng_mode: str | None = RNG_MODE_OPTION,
        field_hints: str | None = cli_common.FIELD_HINTS_OPTION,
        collection_min_items: int | None = cli_common.COLLECTION_MIN_ITEMS_OPTION,
        collection_max_items: int | None = cli_common.COLLECTION_MAX_ITEMS_OPTION,
        collection_distribution: str | None = cli_common.COLLECTION_DISTRIBUTION_OPTION,
        schema: Path | None = SCHEMA_OPTION,
        override_entries: list[str] | None = cli_common.OVERRIDES_OPTION,
        locale: str | None = cli_common.LOCALE_OPTION,
        locale_map_entries: list[str] | None = cli_common.LOCALE_MAP_OPTION,
    ) -> None:
        logger = get_logger()

        if target is None and schema is None:
            render_cli_error(
                DiscoveryError("Provide a module path or use --schema."),
                json_errors=json_errors,
            )
            return

        output_template = OutputTemplate(str(out))

        schema_source_path: Path | None = None
        if schema is not None:
            schema_source_path = schema.resolve()
            if target is not None:
                render_cli_error(
                    DiscoveryError("Provide either a module path or --schema (not both)."),
                    json_errors=json_errors,
                )
                return
            if not schema_source_path.exists():
                render_cli_error(
                    DiscoveryError(
                        f"Schema file '{schema_source_path}' does not exist.",
                        details={"path": str(schema_source_path)},
                    ),
                    json_errors=json_errors,
                )
                return
            try:
                ingestion = SchemaIngester().ingest_json_schema(schema_source_path)
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
                return
            target = str(ingestion.path)

        watch_output: Path | None = None
        watch_extra_paths: list[Path] = []
        if output_template.has_dynamic_directories():
            watch_extra_paths.append(output_template.watch_parent())
        else:
            watch_output = output_template.preview_path()
        if schema_source_path is not None:
            watch_extra_paths.append(schema_source_path)
        watch_extra = watch_extra_paths or None

        module_path = Path(target) if target else None
        field_overrides = cli_common.parse_override_entries(override_entries)
        locale_map = cli_common.parse_locale_entries(locale_map_entries)

        def invoke(exit_app: bool) -> None:
            try:
                _execute_dataset_command(
                    target=target,
                    output_template=output_template,
                    count=count,
                    dataset_format=dataset_format,
                    compression=compression,
                    shard_size=shard_size,
                    include=include,
                    exclude=exclude,
                    seed=seed,
                    now=now,
                    freeze_seeds=freeze_seeds,
                    freeze_seeds_file=freeze_seeds_file,
                    preset=preset,
                    profile=profile,
                    respect_validators=respect_validators,
                    validator_max_retries=validator_max_retries,
                    links=links,
                    max_depth=max_depth,
                    cycle_policy=cycle_policy,
                    rng_mode=rng_mode,
                    logger=logger,
                field_overrides=field_overrides or None,
                field_hints=field_hints,
                collection_min_items=collection_min_items,
                collection_max_items=collection_max_items,
                collection_distribution=collection_distribution,
                locale=locale,
                locale_overrides=locale_map or None,
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
            if module_path is None:
                render_cli_error(
                    DiscoveryError("Watch mode requires a module path."),
                    json_errors=json_errors,
                )
                return
            watch_paths = gather_default_watch_paths(
                module_path,
                output=watch_output,
                extra=watch_extra,
            )
            try:
                logger.debug(
                    "Entering watch loop",
                    event="watch_loop_enter",
                    target=str(target) if target else "<schema>",
                    output=str(watch_output or output_template.preview_path()),
                    debounce=watch_debounce,
                )
                run_with_watch(lambda: invoke(exit_app=False), watch_paths, debounce=watch_debounce)
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
        else:
            invoke(exit_app=True)


def _execute_dataset_command(
    *,
    target: str | None,
    output_template: OutputTemplate,
    count: int,
    dataset_format: str,
    compression: str | None,
    shard_size: int | None,
    include: str | None,
    exclude: str | None,
    seed: int | None,
    now: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None,
    respect_validators: bool | None,
    validator_max_retries: int | None,
    links: list[str] | None,
    max_depth: int | None,
    cycle_policy: str | None,
    rng_mode: str | None,
    logger: Logger,
    field_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    field_hints: str | None = None,
    collection_min_items: int | None = None,
    collection_max_items: int | None = None,
    collection_distribution: str | None = None,
    locale: str | None = None,
    locale_overrides: Mapping[str, str] | None = None,
) -> None:
    if target is None:
        raise DiscoveryError("Target path must be provided when using --schema.")

    include_patterns = cli_common.split_patterns(include)
    exclude_patterns = cli_common.split_patterns(exclude)
    relation_overrides = cli_common.parse_relation_links(links)

    try:
        result = generate_dataset_artifacts(
            target=target,
            output_template=output_template,
            count=count,
            format=dataset_format,
            shard_size=shard_size,
            compression=compression,
            include=include_patterns or None,
            exclude=exclude_patterns or None,
            seed=seed,
            now=now,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_seeds_file,
            preset=preset,
            profile=profile,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            relations=relation_overrides,
            with_related=None,
            logger=logger,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
            field_overrides=field_overrides,
            field_hints=field_hints,
            collection_min_items=collection_min_items,
            collection_max_items=collection_max_items,
            collection_distribution=collection_distribution,
            locale=locale,
            locale_overrides=locale_overrides,
        )
    except PFGError as exc:
        _handle_generation_error(logger, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if isinstance(exc, ConfigError):
            raise
        raise EmitError(str(exc)) from exc

    if _log_dataset_generation_snapshot(logger, result, count):
        return

    emit_constraint_summary(
        result.constraint_summary,
        logger=logger,
        json_mode=logger.config.json,
    )

    for path in result.paths:
        typer.echo(str(path))


def _log_dataset_generation_snapshot(
    logger: Logger,
    result: DatasetGenerationResult,
    count: int,
) -> bool:
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
            "Dataset generation handled by plugin",
            event="dataset_generation_delegated",
            output=str(result.base_output),
            format=result.format,
        )
        return True

    logger.info(
        "Dataset generation complete",
        event="dataset_generation_complete",
        files=[str(path) for path in result.paths],
        count=count,
        format=result.format,
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

    logger.error(
        "Dataset generation failed",
        event="dataset_generation_failed",
        error=str(exc),
        time_anchor=anchor_iso,
    )


__all__ = ["register"]
