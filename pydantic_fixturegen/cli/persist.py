"""CLI command for persisting generated payloads via handlers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.api._runtime import persist_samples
from pydantic_fixturegen.core.errors import PFGError
from pydantic_fixturegen.logging import get_logger

from .gen import _common as cli_common

app = typer.Typer(help="Generate payloads and stream them into persistence handlers.")

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

HANDLER_OPTION = typer.Option(
    ...,
    "--handler",
    "-H",
    help="Registered handler name or dotted path to a handler class/function.",
)

HANDLER_CONFIG_OPTION = typer.Option(
    None,
    "--handler-config",
    help="JSON object containing keyword arguments for the handler.",
)

COUNT_OPTION = typer.Option(1, "--n", "-n", min=1, help="Number of records to generate.")
BATCH_SIZE_OPTION = typer.Option(
    50,
    "--batch-size",
    min=1,
    help="Number of records per handler batch.",
)
MAX_RETRIES_OPTION = typer.Option(
    2,
    "--max-retries",
    min=0,
    help="Maximum attempts per batch before failing.",
)
RETRY_WAIT_OPTION = typer.Option(
    0.5,
    "--retry-wait",
    min=0.0,
    help="Delay between retry attempts in seconds.",
)
INCLUDE_OPTION = typer.Option(
    None,
    "--include",
    "-i",
    help="Comma-separated glob(s) of model names to include.",
)
EXCLUDE_OPTION = typer.Option(
    None,
    "--exclude",
    "-e",
    help="Comma-separated glob(s) of model names to exclude.",
)
SEED_OPTION = typer.Option(None, "--seed", help="Seed override for deterministic generation.")
PRESET_OPTION = typer.Option(None, "--preset", help="Apply a named generation preset.")
PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Apply a privacy profile before other settings.",
)
RESPECT_VALIDATORS_OPTION = typer.Option(
    None,
    "--respect-validators/--no-respect-validators",
    help="Retry generation to satisfy model validators before persistence.",
)
VALIDATOR_MAX_RETRIES_OPTION = typer.Option(
    None,
    "--validator-max-retries",
    min=0,
    help="Maximum additional retry attempts when validators fail.",
)
LINK_OPTION = typer.Option(
    None,
    "--link",
    help="Declare relation link as source.field=target.field (repeatable).",
)
WITH_RELATED_OPTION = typer.Option(
    None,
    "--with-related",
    help="Comma-separated list (repeatable) of related models to generate with each record.",
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
    help="Cycle handling policy when recursion occurs (reuse, stub, null).",
)


def _parse_handler_config(raw: str | None) -> Mapping[str, Any] | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - exercised in CLI tests
        raise typer.BadParameter("handler-config must be valid JSON.") from exc
    if not isinstance(data, Mapping):
        raise typer.BadParameter("handler-config must be a JSON object.")
    return data


@app.command()
def persist(  # noqa: PLR0913 - CLI mirrors documented parameters
    target: Path = TARGET_ARGUMENT,
    handler: str = HANDLER_OPTION,
    handler_config: str | None = HANDLER_CONFIG_OPTION,
    count: int = COUNT_OPTION,
    batch_size: int = BATCH_SIZE_OPTION,
    max_retries: int = MAX_RETRIES_OPTION,
    retry_wait: float = RETRY_WAIT_OPTION,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    seed: int | None = SEED_OPTION,
    now: str | None = cli_common.NOW_OPTION,
    preset: str | None = PRESET_OPTION,
    profile: str | None = PROFILE_OPTION,
    respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
    validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
    links: list[str] | None = LINK_OPTION,
    with_related: list[str] | None = WITH_RELATED_OPTION,
    max_depth: int | None = MAX_DEPTH_OPTION,
    cycle_policy: str | None = CYCLE_POLICY_OPTION,
    rng_mode: str | None = cli_common.RNG_MODE_OPTION,
    field_hints: str | None = cli_common.FIELD_HINTS_OPTION,
    collection_min_items: int | None = cli_common.COLLECTION_MIN_ITEMS_OPTION,
    collection_max_items: int | None = cli_common.COLLECTION_MAX_ITEMS_OPTION,
    collection_distribution: str | None = cli_common.COLLECTION_DISTRIBUTION_OPTION,
    override_entries: list[str] | None = cli_common.OVERRIDES_OPTION,
    json_errors: bool = cli_common.JSON_ERRORS_OPTION,
    locale: str | None = cli_common.LOCALE_OPTION,
    locale_map_entries: list[str] | None = cli_common.LOCALE_MAP_OPTION,
) -> None:
    logger = get_logger()
    handler_options = _parse_handler_config(handler_config)
    include_patterns = cli_common.split_patterns(include)
    exclude_patterns = cli_common.split_patterns(exclude)
    relations = cli_common.parse_relation_links(links)

    related_patterns: list[str] = []
    if with_related:
        for entry in with_related:
            related_patterns.extend(cli_common.split_patterns(entry))

    field_overrides = cli_common.parse_override_entries(override_entries)
    locale_map = cli_common.parse_locale_entries(locale_map_entries)

    try:
        result = persist_samples(
            target=target,
            handler=handler,
            count=count,
            batch_size=batch_size,
            max_retries=max_retries,
            retry_wait=retry_wait,
            handler_options=handler_options,
            include=include_patterns or None,
            exclude=exclude_patterns or None,
            seed=seed,
            now=now,
            preset=preset,
            profile=profile,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            field_overrides=field_overrides or None,
            field_hints=field_hints,
            relations=relations or None,
            with_related=related_patterns or None,
            max_depth=max_depth,
            cycle_policy=cycle_policy,
            rng_mode=rng_mode,
            collection_min_items=collection_min_items,
            collection_max_items=collection_max_items,
            collection_distribution=collection_distribution,
            locale=locale,
            locale_overrides=locale_map or None,
        )
    except PFGError as exc:
        cli_common.render_cli_error(exc, json_errors=json_errors)
        return

    logger.info(
        "Persistence complete",
        event="persistence_complete",
        handler=result.handler,
        batches=result.batches,
        records=result.records,
        retries=result.retries,
        duration=f"{result.duration:.3f}",
    )


__all__ = ["app"]
