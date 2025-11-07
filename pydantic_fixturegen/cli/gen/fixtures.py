"""CLI command for emitting pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import typer

from pydantic_fixturegen.api._runtime import generate_fixtures_artifacts
from pydantic_fixturegen.api.models import FixturesGenerationResult
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.path_template import OutputTemplate

from ...logging import Logger, get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from . import _common as cli_common
from ._common import JSON_ERRORS_OPTION, NOW_OPTION, emit_constraint_summary, render_cli_error

STYLE_CHOICES = {"functions", "factory", "class"}
SCOPE_CHOICES = {"function", "module", "session"}
RETURN_CHOICES = {"model", "dict"}

StyleLiteral = Literal["functions", "factory", "class"]
ReturnLiteral = Literal["model", "dict"]
DEFAULT_RETURN: ReturnLiteral = "model"

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

OUT_OPTION = typer.Option(
    ...,
    "--out",
    "-o",
    help="Output file path for generated fixtures.",
)

STYLE_OPTION = typer.Option(
    None,
    "--style",
    help="Fixture style (functions, factory, class).",
)

SCOPE_OPTION = typer.Option(
    None,
    "--scope",
    help="Fixture scope (function, module, session).",
)

CASES_OPTION = typer.Option(
    1,
    "--cases",
    min=1,
    help="Number of cases per fixture (parametrization size).",
)

RETURN_OPTION = typer.Option(
    None,
    "--return-type",
    help="Return type: model or dict.",
)

SEED_OPTION = typer.Option(
    None,
    "--seed",
    help="Seed override for deterministic generation.",
)

P_NONE_OPTION = typer.Option(
    None,
    "--p-none",
    min=0.0,
    max=1.0,
    help="Probability of None for optional fields.",
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

FREEZE_SEEDS_OPTION = typer.Option(
    False,
    "--freeze-seeds/--no-freeze-seeds",
    help="Read/write per-model seeds using a freeze file to stabilize fixture output.",
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

RESPECT_VALIDATORS_OPTION = typer.Option(
    None,
    "--respect-validators/--no-respect-validators",
    help="Retry instance generation to satisfy validators before emitting fixtures.",
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
        "Comma-separated list (repeatable) of additional models to include alongside the base"
        " selection."
    ),
)


def register(app: typer.Typer) -> None:
    @app.command("fixtures")
    def gen_fixtures(  # noqa: PLR0915 - CLI mirrors documented parameters
        target: str = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        style: str | None = STYLE_OPTION,
        scope: str | None = SCOPE_OPTION,
        cases: int = CASES_OPTION,
        return_type: str | None = RETURN_OPTION,
        seed: int | None = SEED_OPTION,
        now: str | None = NOW_OPTION,
        p_none: float | None = P_NONE_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
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
        with_related: list[str] | None = WITH_RELATED_OPTION,
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
                _execute_fixtures_command(
                    target=target,
                    output_template=output_template,
                    style=style,
                    scope=scope,
                    cases=cases,
                    return_type=return_type,
                    seed=seed,
                    now=now,
                    p_none=p_none,
                    include=include,
                    exclude=exclude,
                    freeze_seeds=freeze_seeds,
                    freeze_seeds_file=freeze_seeds_file,
                    preset=preset,
                    profile=profile,
                    respect_validators=respect_validators,
                    validator_max_retries=validator_max_retries,
                    links=links,
                    with_related=with_related,
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


def _execute_fixtures_command(
    *,
    target: str,
    output_template: OutputTemplate,
    style: str | None,
    scope: str | None,
    cases: int,
    return_type: str | None,
    seed: int | None,
    now: str | None,
    p_none: float | None,
    include: str | None,
    exclude: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None = None,
    respect_validators: bool | None = None,
    validator_max_retries: int | None = None,
    links: list[str] | None = None,
    with_related: list[str] | None = None,
) -> None:
    logger = get_logger()

    style_value = _coerce_style(style)
    scope_value = _coerce_scope(scope)
    return_type_value = _coerce_return_type(return_type)

    include_patterns = cli_common.split_patterns(include)
    exclude_patterns = cli_common.split_patterns(exclude)
    related_identifiers: list[str] = []
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

    try:
        result = generate_fixtures_artifacts(
            target=target,
            output_template=output_template,
            style=style_value,
            scope=scope_value,
            cases=cases,
            return_type=return_type_value,
            seed=seed,
            now=now,
            p_none=p_none,
            include=include_values,
            exclude=exclude_values,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_seeds_file,
            preset=preset,
            profile=profile,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            relations=cli_common.parse_relation_links(links),
            with_related=related_identifiers or None,
            logger=logger,
        )
    except PFGError as exc:
        _handle_fixtures_error(logger, exc)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if isinstance(exc, ConfigError):
            raise
        raise EmitError(str(exc)) from exc

    if _log_fixtures_snapshot(logger, result):
        return

    emit_constraint_summary(
        result.constraint_summary,
        logger=logger,
        json_mode=logger.config.json,
    )

    output_path = result.path or result.base_output
    message = str(output_path)
    if result.skipped:
        message += " (unchanged)"
    typer.echo(message)


def _log_fixtures_snapshot(logger: Logger, result: FixturesGenerationResult) -> bool:
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
            "Fixtures generation handled by plugin",
            event="fixtures_generation_delegated",
            output=str(result.base_output),
            style=result.style,
            scope=result.scope,
            time_anchor=anchor_iso,
        )
        return True

    if result.skipped:
        logger.info(
            "Fixtures unchanged",
            event="fixtures_generation_unchanged",
            output=str(result.path),
            time_anchor=anchor_iso,
        )
    else:
        logger.info(
            "Fixtures generation complete",
            event="fixtures_generation_complete",
            output=str(result.path),
            style=result.style,
            scope=result.scope,
            time_anchor=anchor_iso,
        )
    return False


__all__ = ["register"]


def _handle_fixtures_error(logger: Logger, exc: PFGError) -> None:
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


def _coerce_style(value: str | None) -> StyleLiteral | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered not in STYLE_CHOICES:
        raise DiscoveryError(
            f"Invalid style '{value}'.",
            details={"style": value},
        )
    return cast(StyleLiteral, lowered)


def _coerce_scope(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered not in SCOPE_CHOICES:
        raise DiscoveryError(
            f"Invalid scope '{value}'.",
            details={"scope": value},
        )
    return lowered


def _coerce_return_type(value: str | None) -> ReturnLiteral | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered not in RETURN_CHOICES:
        raise DiscoveryError(
            f"Invalid return type '{value}'.",
            details={"return_type": value},
        )
    return cast(ReturnLiteral, lowered)
