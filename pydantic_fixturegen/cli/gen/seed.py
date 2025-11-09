"""CLI commands for database seeding."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import typer

from pydantic_fixturegen.api._runtime import (
    ModelArtifactPlan,
    _build_model_artifact_plan,
)
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.core.schema_ingest import SchemaIngester
from pydantic_fixturegen.logging import Logger, get_logger

from . import _common as cli_common
from ._common import (
    JSON_ERRORS_OPTION,
    NOW_OPTION,
    RNG_MODE_OPTION,
    render_cli_error,
)

seed_app = typer.Typer(help="Seed integration databases via supported ORMs.")

TARGET_ARGUMENT = typer.Argument(
    None,
    help=(
        "Path to a Python module containing SQLModel/Beanie models (optional when using --schema)."
    ),
)

DATABASE_OPTION = typer.Option(
    ...,
    "--database",
    "-d",
    help="Database URL (e.g. sqlite:///app.db, mongodb://localhost:27017/app).",
)

SQLMODEL_ALLOW_URL_OPTION = typer.Option(
    ["sqlite://", "sqlite:///"],
    "--allow-url",
    help="Allowed SQL connection URL prefix (repeatable).",
)

BEANIE_ALLOW_URL_OPTION = typer.Option(
    ["mongodb://", "mongomock://"],
    "--allow-url",
    help="Allowed MongoDB connection URL prefix (repeatable).",
)

COUNT_OPTION = typer.Option(
    1,
    "--n",
    "-n",
    min=1,
    help="Number of primary records to generate per run.",
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

FREEZE_SEEDS_OPTION = typer.Option(
    False,
    "--freeze-seeds/--no-freeze-seeds",
    help="Read/write per-model seeds using a freeze file.",
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
    help="Retry generation to satisfy validators.",
)

VALIDATOR_MAX_RETRIES_OPTION = typer.Option(
    None,
    "--validator-max-retries",
    min=0,
    help="Maximum validator retries when respect-validators is enabled.",
)

LINK_OPTION = typer.Option(
    None,
    "--link",
    help="Relation mapping formatted as source.field=target.field (repeatable).",
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

SCHEMA_OPTION = typer.Option(
    None,
    "--schema",
    help="Path to a JSON Schema document to ingest before generation.",
)

BATCH_OPTION = typer.Option(
    50,
    "--batch-size",
    min=1,
    help="Number of samples to generate per transaction batch.",
)

ROLLBACK_OPTION = typer.Option(
    False,
    "--rollback/--commit",
    help="Generate records inside a transaction that rolls back at the end (default commit).",
)

DRY_RUN_OPTION = typer.Option(
    False,
    "--dry-run",
    help="Log generated payloads without inserting into the database.",
)

TRUNCATE_OPTION = typer.Option(
    False,
    "--truncate/--no-truncate",
    help="Delete existing rows for the selected models before seeding.",
)

CREATE_SCHEMA_OPTION = typer.Option(
    False,
    "--create-schema/--no-create-schema",
    help="Create SQLModel tables before seeding.",
)

ECHO_OPTION = typer.Option(
    False,
    "--echo/--no-echo",
    help="Enable SQLAlchemy echo logging when creating the engine.",
)

CLEANUP_OPTION = typer.Option(
    False,
    "--cleanup/--keep",
    help="For Beanie, delete inserted documents after seeding (wraps each insert in delete).",
)


@seed_app.command("sqlmodel")
def seed_sqlmodel(  # noqa: PLR0913
    target: str | None = TARGET_ARGUMENT,
    database: str = DATABASE_OPTION,
    count: int = COUNT_OPTION,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    seed: int | None = SEED_OPTION,
    now: str | None = NOW_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
    freeze_seeds: bool = FREEZE_SEEDS_OPTION,
    freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
    preset: str | None = PRESET_OPTION,
    profile: str | None = PROFILE_OPTION,
    respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
    validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
    links: list[str] | None = LINK_OPTION,
    with_related: list[str] | None = WITH_RELATED_OPTION,
    max_depth: int | None = MAX_DEPTH_OPTION,
    cycle_policy: str | None = CYCLE_POLICY_OPTION,
    rng_mode: str | None = RNG_MODE_OPTION,
    schema: Path | None = SCHEMA_OPTION,
    batch_size: int = BATCH_OPTION,
    rollback: bool = ROLLBACK_OPTION,
    dry_run: bool = DRY_RUN_OPTION,
    truncate: bool = TRUNCATE_OPTION,
    create_schema: bool = CREATE_SCHEMA_OPTION,
    echo: bool = ECHO_OPTION,
    allow_url: list[str] = SQLMODEL_ALLOW_URL_OPTION,
) -> None:
    logger = get_logger()
    from pydantic_fixturegen.orm.sqlalchemy import SQLAlchemySeeder

    dispose_engine: Callable[[], None] | None = None
    try:
        _validate_connection(database, allow_url)
        module_path = _resolve_target_module(target, schema)
        plan = _create_plan(
            module_path=module_path,
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
            with_related=with_related,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
            logger=logger,
        )
        session_factory, dispose_engine = _build_sqlmodel_session_factory(
            database,
            echo=echo,
            create_schema=create_schema,
        )
        seeder = SQLAlchemySeeder(plan, session_factory, logger=logger)
        result = seeder.seed(
            count=count,
            batch_size=batch_size,
            rollback=rollback,
            dry_run=dry_run,
            truncate=truncate,
        )
        _log_seed_summary(
            logger,
            result.inserted,
            rollback=result.rollback,
            dry_run=result.dry_run,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
    except ConfigError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
    except Exception as exc:  # pragma: no cover - defensive
        render_cli_error(EmitError(str(exc)), json_errors=json_errors)
    finally:
        if dispose_engine is not None:
            dispose_engine()


@seed_app.command("beanie")
def seed_beanie(  # noqa: PLR0913
    target: str | None = TARGET_ARGUMENT,
    database: str = DATABASE_OPTION,
    count: int = COUNT_OPTION,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    seed: int | None = SEED_OPTION,
    now: str | None = NOW_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
    freeze_seeds: bool = FREEZE_SEEDS_OPTION,
    freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
    preset: str | None = PRESET_OPTION,
    profile: str | None = PROFILE_OPTION,
    respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
    validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
    links: list[str] | None = LINK_OPTION,
    with_related: list[str] | None = WITH_RELATED_OPTION,
    max_depth: int | None = MAX_DEPTH_OPTION,
    cycle_policy: str | None = CYCLE_POLICY_OPTION,
    rng_mode: str | None = RNG_MODE_OPTION,
    schema: Path | None = SCHEMA_OPTION,
    batch_size: int = BATCH_OPTION,
    cleanup: bool = CLEANUP_OPTION,
    dry_run: bool = DRY_RUN_OPTION,
    allow_url: list[str] = BEANIE_ALLOW_URL_OPTION,
) -> None:
    logger = get_logger()
    from pydantic_fixturegen.orm.beanie import BeanieSeeder

    try:
        _validate_connection(database, allow_url)
        module_path = _resolve_target_module(target, schema)
        plan = _create_plan(
            module_path=module_path,
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
            with_related=with_related,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
            logger=logger,
        )
        database_name = _mongo_database_name(database)

        def client_factory() -> Any:
            return _create_beanie_client(database)

        seeder = BeanieSeeder(plan, client_factory, database_name=database_name, logger=logger)
        warning_category: type[Warning] = DeprecationWarning
        try:  # pragma: no cover - narrow import path
            from pydantic.warnings import PydanticDeprecatedSince211

            warning_category = PydanticDeprecatedSince211
        except Exception:  # noqa: BLE001 - fall back to DeprecationWarning
            pass
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=warning_category,
                message=r"Accessing the 'model_fields' attribute on the instance is deprecated.*",
            )
            result = seeder.seed(
                count=count,
                batch_size=batch_size,
                cleanup=cleanup,
                dry_run=dry_run,
            )
        _log_seed_summary(
            logger,
            result.inserted,
            cleanup=cleanup,
            dry_run=result.dry_run,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
    except ConfigError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
    except Exception as exc:  # pragma: no cover - defensive
        render_cli_error(EmitError(str(exc)), json_errors=json_errors)


def _resolve_target_module(target: str | None, schema: Path | None) -> Path:
    if target is None and schema is None:
        raise DiscoveryError("Provide a module path or use --schema.")

    if schema is None:
        return Path(target).resolve()  # type: ignore[arg-type]

    schema_path = schema.resolve()
    if target is not None:
        raise DiscoveryError("Provide either a module path or --schema (not both).")
    if not schema_path.exists():
        raise DiscoveryError(f"Schema file '{schema_path}' does not exist.")
    ingestion = SchemaIngester().ingest_json_schema(schema_path)
    return ingestion.path


def _create_plan(
    *,
    module_path: Path,
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
    with_related: list[str] | None,
    max_depth: int | None,
    cycle_policy: str | None,
    rng_mode: str | None,
    logger: Logger,
) -> ModelArtifactPlan:
    include_patterns = cli_common.split_patterns(include)
    exclude_patterns = cli_common.split_patterns(exclude)
    relation_overrides = cli_common.parse_relation_links(links)
    related_identifiers: list[str] | None = None
    if with_related:
        related_identifiers = []
        for entry in with_related:
            related_identifiers.extend(cli_common.split_patterns(entry))
    output_template = OutputTemplate(str(module_path.with_suffix(".seed.json")))
    return _build_model_artifact_plan(
        target_path=module_path,
        output_template=output_template,
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
        with_related=related_identifiers,
        logger=logger,
        max_depth=max_depth,
        cycle_policy=cycle_policy,
        rng_mode=rng_mode,
        payload_mode="python",
    )


def _validate_connection(database: str, allowlist: list[str]) -> None:
    if not allowlist:
        return
    if any(database.startswith(prefix) for prefix in allowlist):
        return
    allowed = ", ".join(allowlist)
    raise DiscoveryError(
        f"Connection URL '{database}' is not allowed. Provide --allow-url to extend the allowlist.",
        details={"allowed": allowed},
    )


def _build_sqlmodel_session_factory(
    database: str,
    *,
    echo: bool,
    create_schema: bool,
) -> tuple[Callable[[], Any], Callable[[], None]]:
    import sqlmodel

    engine = sqlmodel.create_engine(database, echo=echo)
    if create_schema:
        sqlmodel.SQLModel.metadata.create_all(engine)

    def _factory() -> Any:
        return sqlmodel.Session(engine)

    def _dispose() -> None:
        engine.dispose()

    return _factory, _dispose


def _create_beanie_client(database: str) -> Any:
    from motor.motor_asyncio import AsyncIOMotorClient

    return AsyncIOMotorClient(database)


def _mongo_database_name(database: str) -> str:
    parsed = urlparse(database)
    db_name = parsed.path.strip("/")
    if not db_name:
        raise DiscoveryError(
            "MongoDB connection URL must include a database name (e.g. mongodb://localhost/app)"
        )
    return db_name


def _log_seed_summary(
    logger: Logger,
    inserted: int,
    *,
    rollback: bool = False,
    cleanup: bool = False,
    dry_run: bool,
) -> None:
    logger.info(
        "Database seeding complete",
        event="seed_generation_complete",
        inserted=inserted,
        rollback=rollback,
        cleanup=cleanup,
        dry_run=dry_run,
    )


__all__ = ["seed_app"]
