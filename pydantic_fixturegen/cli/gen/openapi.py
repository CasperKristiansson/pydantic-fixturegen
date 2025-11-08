"""CLI command for emitting samples from OpenAPI documents."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.api._runtime import generate_json_artifacts
from pydantic_fixturegen.api.models import JsonGenerationResult
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.openapi import (
    dump_document,
    load_openapi_document,
    parse_route_value,
    select_openapi_schemas,
)
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.core.schema_ingest import SchemaIngester

from ...logging import Logger, get_logger
from ._common import (
    JSON_ERRORS_OPTION,
    NOW_OPTION,
    RNG_MODE_OPTION,
    emit_constraint_summary,
    render_cli_error,
)
from .json import (
    COUNT_OPTION,
    CYCLE_POLICY_OPTION,
    FREEZE_FILE_OPTION,
    FREEZE_SEEDS_OPTION,
    INDENT_OPTION,
    JSONL_OPTION,
    MAX_DEPTH_OPTION,
    ORJSON_OPTION,
    OUT_OPTION,
    PRESET_OPTION,
    PROFILE_OPTION,
    RESPECT_VALIDATORS_OPTION,
    SEED_OPTION,
    SHARD_OPTION,
    VALIDATOR_MAX_RETRIES_OPTION,
    _handle_generation_error,
    _log_generation_snapshot,
)

SPEC_ARGUMENT = typer.Argument(..., help="Path to an OpenAPI 3.x document (YAML or JSON).")

ROUTE_OPTION = typer.Option(
    None,
    "--route",
    help="Limit generation to a specific HTTP method and path (e.g. 'GET /users').",
)


def register(app: typer.Typer) -> None:
    @app.command("openapi")
    def gen_openapi(
        spec: Path = SPEC_ARGUMENT,
        routes: list[str] | None = ROUTE_OPTION,
        out: Path = OUT_OPTION,
        count: int = COUNT_OPTION,
        jsonl: bool = JSONL_OPTION,
        indent: int | None = INDENT_OPTION,
        use_orjson: bool | None = ORJSON_OPTION,
        shard_size: int | None = SHARD_OPTION,
        seed: int | None = SEED_OPTION,
        now: str | None = NOW_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
        freeze_seeds: bool = FREEZE_SEEDS_OPTION,
        freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
        preset: str | None = PRESET_OPTION,
        profile: str | None = PROFILE_OPTION,
        respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
        validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
        max_depth: int | None = MAX_DEPTH_OPTION,
        cycle_policy: str | None = CYCLE_POLICY_OPTION,
        rng_mode: str | None = RNG_MODE_OPTION,
    ) -> None:
        logger = get_logger()

        try:
            parsed_routes = (
                [parse_route_value(value) for value in routes] if routes else None
            )
        except ValueError as exc:
            render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
            return

        try:
            document = load_openapi_document(spec)
            selection = select_openapi_schemas(document, parsed_routes)
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
            return

        try:
            output_template = OutputTemplate(str(out))
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
            return

        if len(selection.schemas) > 1 and "model" not in output_template.fields:
            render_cli_error(
                DiscoveryError(
                    "Output template must include '{model}' when emitting multiple schemas.",
                    hint="For example: --out 'openapi/{model}.json'",
                ),
                json_errors=json_errors,
            )
            return

        ingester = SchemaIngester()
        try:
            module_info = ingester.ingest_openapi(
                spec.resolve(),
                document_bytes=dump_document(selection.document),
                fingerprint=selection.fingerprint(),
            )
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
            return

        for schema_name in selection.schemas:
            include_pattern = f"*.{schema_name}"
            try:
                result = _generate_for_schema(
                    schema_name,
                    module_path=module_info.path,
                    include_pattern=include_pattern,
                    output_template=output_template,
                    count=count,
                    jsonl=jsonl,
                    indent=indent,
                    use_orjson=use_orjson,
                    shard_size=shard_size,
                    seed=seed,
                    now=now,
                    freeze_seeds=freeze_seeds,
                    freeze_seeds_file=freeze_seeds_file,
                    preset=preset,
                    profile=profile,
                    respect_validators=respect_validators,
                    validator_max_retries=validator_max_retries,
                    max_depth=max_depth,
                    cycle_policy=cycle_policy,
                    rng_mode=rng_mode,
                    logger=logger,
                )
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
                return

            if _log_generation_snapshot(logger, result, count):
                continue

            emit_constraint_summary(
                result.constraint_summary,
                logger=logger,
                json_mode=logger.config.json,
            )

            for emitted_path in result.paths:
                typer.echo(str(emitted_path))


def _generate_for_schema(
    schema_name: str,
    *,
    module_path: Path,
    include_pattern: str,
    output_template: OutputTemplate,
    count: int,
    jsonl: bool,
    indent: int | None,
    use_orjson: bool | None,
    shard_size: int | None,
    seed: int | None,
    now: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None,
    respect_validators: bool | None,
    validator_max_retries: int | None,
    max_depth: int | None,
    cycle_policy: str | None,
    rng_mode: str | None,
    logger: Logger,
) -> JsonGenerationResult:
    try:
        return generate_json_artifacts(
            target=str(module_path),
            output_template=output_template,
            count=count,
            jsonl=jsonl,
            indent=indent,
            use_orjson=use_orjson,
            shard_size=shard_size,
            include=[include_pattern],
            exclude=None,
            seed=seed,
            now=now,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_seeds_file,
            preset=preset,
            profile=profile,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            relations=None,
            with_related=None,
            type_annotation=None,
            type_label=None,
            logger=logger,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
        )
    except PFGError as exc:
        _handle_generation_error(logger, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if isinstance(exc, ConfigError):
            raise
        raise EmitError(str(exc)) from exc


__all__ = ["register"]
