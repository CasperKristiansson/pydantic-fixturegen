"""CLI command for emitting pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import typer

from pydantic_fixturegen.core.config import ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.core.seed_freeze import (
    FreezeStatus,
    SeedFreezeFile,
    compute_model_digest,
    derive_default_model_seed,
    model_identifier,
    resolve_freeze_path,
)
from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ...logging import get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from ._common import (
    JSON_ERRORS_OPTION,
    clear_module_cache,
    discover_models,
    emit_constraint_summary,
    load_model_class,
    render_cli_error,
    split_patterns,
)

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
        p_none: float | None = P_NONE_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
        watch: bool = WATCH_OPTION,
        watch_debounce: float = WATCH_DEBOUNCE_OPTION,
        freeze_seeds: bool = FREEZE_SEEDS_OPTION,
        freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
        preset: str | None = PRESET_OPTION,
    ) -> None:
        logger = get_logger()

        def invoke(exit_app: bool) -> None:
            try:
                _execute_fixtures_command(
                    target=target,
                    out=out,
                    style=style,
                    scope=scope,
                    cases=cases,
                    return_type=return_type,
                    seed=seed,
                    p_none=p_none,
                    include=include,
                    exclude=exclude,
                    freeze_seeds=freeze_seeds,
                    freeze_seeds_file=freeze_seeds_file,
                    preset=preset,
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
            watch_paths = gather_default_watch_paths(Path(target), output=out)
            try:
                logger.debug(
                    "Entering watch loop",
                    event="watch_loop_enter",
                    target=str(target),
                    output=str(out),
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
    out: Path,
    style: str | None,
    scope: str | None,
    cases: int,
    return_type: str | None,
    seed: int | None,
    p_none: float | None,
    include: str | None,
    exclude: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
) -> None:
    logger = get_logger()
    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    style_value = _coerce_style(style)
    scope_value = _coerce_scope(scope)
    return_type_value = _coerce_return_type(return_type)

    clear_module_cache()
    load_entrypoint_plugins()

    freeze_manager: SeedFreezeFile | None = None
    if freeze_seeds:
        freeze_path = resolve_freeze_path(freeze_seeds_file, root=Path.cwd())
        freeze_manager = SeedFreezeFile.load(freeze_path)
        for message in freeze_manager.messages:
            logger.warn(
                "Seed freeze file ignored",
                event="seed_freeze_invalid",
                path=str(freeze_path),
                reason=message,
            )

    cli_overrides: dict[str, Any] = {}
    if preset is not None:
        cli_overrides["preset"] = preset
    if seed is not None:
        cli_overrides["seed"] = seed
    if p_none is not None:
        cli_overrides["p_none"] = p_none
    emitter_overrides: dict[str, Any] = {}
    if style_value is not None:
        emitter_overrides["style"] = style_value
    if scope_value is not None:
        emitter_overrides["scope"] = scope_value
    if emitter_overrides:
        cli_overrides["emitters"] = {"pytest": emitter_overrides}
    if include:
        cli_overrides["include"] = split_patterns(include)
    if exclude:
        cli_overrides["exclude"] = split_patterns(exclude)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)

    logger.debug(
        "Loaded configuration",
        event="config_loaded",
        seed=app_config.seed,
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

    seed_value: int | None = None
    if app_config.seed is not None:
        seed_value = SeedManager(seed=app_config.seed).normalized_seed

    style_final = style_value or cast(StyleLiteral, app_config.emitters.pytest.style)
    scope_final = scope_value or app_config.emitters.pytest.scope
    return_type_final = return_type_value or DEFAULT_RETURN

    per_model_seeds: dict[str, int] = {}
    model_digests: dict[str, str | None] = {}

    for model_cls in model_classes:
        model_id = model_identifier(model_cls)
        digest = compute_model_digest(model_cls)
        model_digests[model_id] = digest

        if freeze_manager is not None:
            default_seed = derive_default_model_seed(app_config.seed, model_id)
            selected_seed = default_seed

            stored_seed, status = freeze_manager.resolve_seed(model_id, model_digest=digest)
            if status is FreezeStatus.VALID and stored_seed is not None:
                selected_seed = stored_seed
            else:
                event = (
                    "seed_freeze_missing" if status is FreezeStatus.MISSING else "seed_freeze_stale"
                )
                logger.warn(
                    "Seed freeze entry unavailable; deriving new seed",
                    event=event,
                    model=model_id,
                    path=str(freeze_manager.path),
                )
                selected_seed = default_seed
        else:
            selected_seed = derive_default_model_seed(app_config.seed, model_id)

        per_model_seeds[model_id] = selected_seed

    header_seed = seed_value if freeze_manager is None else None

    pytest_config = PytestEmitConfig(
        scope=scope_final,
        style=style_final,
        return_type=return_type_final,
        cases=cases,
        seed=header_seed,
        optional_p_none=app_config.p_none,
        per_model_seeds=per_model_seeds if freeze_manager is not None else None,
    )

    context = EmitterContext(
        models=tuple(model_classes),
        output=out,
        parameters={
            "style": style_final,
            "scope": scope_final,
            "cases": cases,
            "return_type": return_type_final,
        },
    )
    if emit_artifact("fixtures", context):
        logger.info(
            "Fixture generation handled by plugin",
            event="fixtures_generation_delegated",
            output=str(out),
            style=style_final,
            scope=scope_final,
        )
        return

    try:
        result = emit_pytest_fixtures(
            model_classes,
            output_path=out,
            config=pytest_config,
        )
    except Exception as exc:
        raise EmitError(str(exc)) from exc

    constraint_summary = None
    if result.metadata and "constraints" in result.metadata:
        constraint_summary = result.metadata["constraints"]

    message = str(out)
    if result.skipped:
        message += " (unchanged)"
        logger.info(
            "Fixtures unchanged",
            event="fixtures_generation_unchanged",
            output=str(out),
        )
    else:
        logger.info(
            "Fixtures generation complete",
            event="fixtures_generation_complete",
            output=str(result.path),
            style=style_final,
            scope=scope_final,
        )
    typer.echo(message)

    emit_constraint_summary(
        constraint_summary,
        logger=logger,
        json_mode=logger.config.json,
    )

    if freeze_manager is not None:
        for model_cls in model_classes:
            model_id = model_identifier(model_cls)
            freeze_manager.record_seed(
                model_id,
                per_model_seeds[model_id],
                model_digest=model_digests[model_id],
            )
        freeze_manager.save()


__all__ = ["register"]


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
