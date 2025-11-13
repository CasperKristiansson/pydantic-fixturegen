"""CLI command for generating JSON/JSONL samples."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen._warnings import apply_warning_filters
from pydantic_fixturegen.api._runtime import generate_json_artifacts
from pydantic_fixturegen.api.models import JsonGenerationResult
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
    help="Path to a Python module containing Pydantic models (optional when using --type).",
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

TYPE_OPTION = typer.Option(
    None,
    "--type",
    help=("Python type expression to generate via TypeAdapter (e.g. 'list[EmailStr]')."),
)

SCHEMA_OPTION = typer.Option(
    None,
    "--schema",
    help="Path to a JSON Schema document to ingest before generation.",
)

RESPECT_VALIDATORS_OPTION = typer.Option(
    None,
    "--respect-validators/--no-respect-validators",
    help="Retry generation to satisfy model validators before emitting samples.",
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

WITH_RELATED_OPTION = typer.Option(
    None,
    "--with-related",
    help=(
        "Comma-separated list (repeatable) of additional models to generate alongside the primary."
    ),
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


def register(app: typer.Typer) -> None:
    @app.command("json")
    def gen_json(  # noqa: PLR0913 - CLI surface mirrors documented parameters
        target: str | None = TARGET_ARGUMENT,
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
        type_expr: str | None = TYPE_OPTION,
        respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
        validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
        links: list[str] | None = LINK_OPTION,
        with_related: list[str] | None = WITH_RELATED_OPTION,
        max_depth: int | None = MAX_DEPTH_OPTION,
        cycle_policy: str | None = CYCLE_POLICY_OPTION,
        rng_mode: str | None = RNG_MODE_OPTION,
        field_hints: str | None = cli_common.FIELD_HINTS_OPTION,
        collection_min_items: int | None = cli_common.COLLECTION_MIN_ITEMS_OPTION,
        collection_max_items: int | None = cli_common.COLLECTION_MAX_ITEMS_OPTION,
        collection_distribution: str | None = cli_common.COLLECTION_DISTRIBUTION_OPTION,
        override_entries: list[str] | None = cli_common.OVERRIDES_OPTION,
        schema: Path | None = SCHEMA_OPTION,
    ) -> None:
        apply_warning_filters()
        logger = get_logger()

        if schema is not None and type_expr is not None:
            render_cli_error(
                DiscoveryError("--schema cannot be combined with --type targets."),
                json_errors=json_errors,
            )
            return

        try:
            output_template = OutputTemplate(str(out))
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
            return

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
        type_annotation: Any | None = None
        if type_expr:
            try:
                type_annotation = cli_common.evaluate_type_expression(
                    type_expr,
                    module_path=module_path,
                )
            except ValueError as exc:
                render_cli_error(
                    DiscoveryError(str(exc)),
                    json_errors=json_errors,
                )
                return

        field_overrides = cli_common.parse_override_entries(override_entries)

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
                    respect_validators=respect_validators,
                    validator_max_retries=validator_max_retries,
                    links=links,
                    with_related=with_related,
                    type_annotation=type_annotation,
                    type_label=type_expr,
                    max_depth=max_depth,
                    cycle_policy=cycle_policy,
                    rng_mode=rng_mode,
                    field_overrides=field_overrides or None,
                    field_hints=field_hints,
                    collection_min_items=collection_min_items,
                    collection_max_items=collection_max_items,
                    collection_distribution=collection_distribution,
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
                    DiscoveryError("Watch mode requires a module path when using --type."),
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
                    target=str(target) if target else "<type-adapter>",
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
    target: str | None,
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
    respect_validators: bool | None = None,
    validator_max_retries: int | None = None,
    links: list[str] | None = None,
    with_related: list[str] | None = None,
    type_annotation: Any | None = None,
    type_label: str | None = None,
    max_depth: int | None = None,
    cycle_policy: str | None = None,
    rng_mode: str | None = None,
    field_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    field_hints: str | None = None,
    collection_min_items: int | None = None,
    collection_max_items: int | None = None,
    collection_distribution: str | None = None,
) -> None:
    logger = get_logger()

    include_values: list[str] | None
    exclude_values: list[str] | None
    related_identifiers: list[str] = []
    relation_overrides: Mapping[str, str] | None = None

    if type_annotation is None:
        include_patterns = cli_common.split_patterns(include)
        exclude_patterns = cli_common.split_patterns(exclude)
        related_include_patterns: list[str] = []
        if with_related:
            for entry in with_related:
                for token in cli_common.split_patterns(entry):
                    related_identifiers.append(token)
                    if any(marker in token for marker in ("*", "?", ".")):
                        related_include_patterns.append(token)
                    else:
                        related_include_patterns.append(f"*.{token}")

        discovery_includes = list(include_patterns)
        if related_include_patterns:
            discovery_includes.extend(related_include_patterns)

        include_values = discovery_includes or None
        exclude_values = exclude_patterns or None
        relation_overrides = cli_common.parse_relation_links(links)
    else:
        if links:
            raise DiscoveryError("--link is not supported when using --type.")
        if with_related:
            raise DiscoveryError("--with-related is not supported when using --type.")
        include_values = None
        exclude_values = None

    try:
        result = generate_json_artifacts(
            target=target,
            output_template=output_template,
            count=count,
            jsonl=jsonl,
            indent=indent,
            use_orjson=use_orjson,
            shard_size=shard_size,
            include=include_values,
            exclude=exclude_values,
            seed=seed,
            now=now,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_seeds_file,
            preset=preset,
            profile=profile,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            relations=relation_overrides,
            with_related=related_identifiers or None,
            type_annotation=type_annotation,
            type_label=type_label,
            logger=logger,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
            field_overrides=field_overrides or None,
            field_hints=field_hints,
            collection_min_items=collection_min_items,
            collection_max_items=collection_max_items,
            collection_distribution=collection_distribution,
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
