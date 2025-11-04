"""CLI command for generating JSON/JSONL samples."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.config import AppConfig, ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, MappingError, PFGError
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.core.seed_freeze import (
    FreezeStatus,
    SeedFreezeFile,
    compute_model_digest,
    derive_default_model_seed,
    model_identifier,
    resolve_freeze_path,
)
from pydantic_fixturegen.emitters.json_out import emit_json_samples
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ...logging import get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from ._common import (
    JSON_ERRORS_OPTION,
    NOW_OPTION,
    clear_module_cache,
    discover_models,
    emit_constraint_summary,
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
    ) -> None:
        logger = get_logger()

        def invoke(exit_app: bool) -> None:
            try:
                _execute_json_command(
                    target=target,
                    out=out,
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


def _execute_json_command(
    *,
    target: str,
    out: Path,
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
) -> None:
    logger = get_logger()
    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

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
    if now is not None:
        cli_overrides["now"] = now
    json_overrides: dict[str, Any] = {}
    if indent is not None:
        json_overrides["indent"] = indent
    if use_orjson is not None:
        json_overrides["orjson"] = use_orjson
    if json_overrides:
        cli_overrides["json"] = json_overrides
    if include:
        cli_overrides["include"] = split_patterns(include)
    if exclude:
        cli_overrides["exclude"] = split_patterns(exclude)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)

    anchor_iso = app_config.now.isoformat() if app_config.now else None

    logger.debug(
        "Loaded configuration",
        event="config_loaded",
        seed=app_config.seed,
        include=list(app_config.include),
        exclude=list(app_config.exclude),
        time_anchor=anchor_iso,
    )

    if anchor_iso:
        logger.info(
            "Using temporal anchor",
            event="temporal_anchor_set",
            time_anchor=anchor_iso,
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

    if len(discovery.models) > 1:
        names = ", ".join(model.qualname for model in discovery.models)
        raise DiscoveryError(
            f"Multiple models discovered ({names}). Use --include/--exclude to narrow selection.",
            details={"models": names},
        )

    target_model = discovery.models[0]

    try:
        model_cls = load_model_class(target_model)
    except RuntimeError as exc:
        raise DiscoveryError(str(exc)) from exc

    model_id = model_identifier(model_cls)
    model_digest = compute_model_digest(model_cls)

    if freeze_manager is not None:
        default_seed = derive_default_model_seed(app_config.seed, model_id)
        selected_seed: int | None = default_seed
        stored_seed, status = freeze_manager.resolve_seed(model_id, model_digest=model_digest)
        if status is FreezeStatus.VALID and stored_seed is not None:
            selected_seed = stored_seed
        else:
            event = "seed_freeze_missing" if status is FreezeStatus.MISSING else "seed_freeze_stale"
            logger.warn(
                "Seed freeze entry unavailable; deriving new seed",
                event=event,
                model=model_id,
                path=str(freeze_manager.path),
            )
            selected_seed = default_seed
    else:
        selected_seed = None

    generator = _build_instance_generator(app_config, seed_override=selected_seed)

    def sample_factory() -> BaseModel:
        instance = generator.generate_one(model_cls)
        if instance is None:
            raise MappingError(
                f"Failed to generate instance for {target_model.qualname}.",
                details={"model": target_model.qualname},
            )
        return instance

    indent_value = indent if indent is not None else app_config.json.indent
    use_orjson_value = use_orjson if use_orjson is not None else app_config.json.orjson

    context = EmitterContext(
        models=(model_cls,),
        output=out,
        parameters={
            "count": count,
            "jsonl": jsonl,
            "indent": indent_value,
            "shard_size": shard_size,
            "use_orjson": use_orjson_value,
        },
    )
    if emit_artifact("json", context):
        logger.info(
            "JSON generation handled by plugin",
            event="json_generation_delegated",
            output=str(out),
            time_anchor=anchor_iso,
        )
        return

    try:
        paths = emit_json_samples(
            sample_factory,
            output_path=out,
            count=count,
            jsonl=jsonl,
            indent=indent_value,
            shard_size=shard_size,
            use_orjson=use_orjson_value,
            ensure_ascii=False,
        )
    except RuntimeError as exc:
        constraint_summary = _summarize_constraint_report(generator)
        emit_constraint_summary(
            constraint_summary,
            logger=logger,
            json_mode=logger.config.json,
        )
        raise EmitError(str(exc)) from exc
    except PFGError:
        constraint_summary = _summarize_constraint_report(generator)
        emit_constraint_summary(
            constraint_summary,
            logger=logger,
            json_mode=logger.config.json,
        )
        raise
    else:
        constraint_summary = _summarize_constraint_report(generator)
        path_strs = [str(emitted_path) for emitted_path in paths]
        logger.info(
            "JSON generation complete",
            event="json_generation_complete",
            files=path_strs,
            count=count,
            time_anchor=anchor_iso,
        )
        emit_constraint_summary(
            constraint_summary,
            logger=logger,
            json_mode=logger.config.json,
        )
    if freeze_manager is not None:
        assert selected_seed is not None
        freeze_manager.record_seed(model_id, selected_seed, model_digest=model_digest)
        freeze_manager.save()
    for emitted_path in paths:
        typer.echo(str(emitted_path))


def _summarize_constraint_report(generator: Any) -> dict[str, Any] | None:
    reporter = getattr(generator, "constraint_report", None)
    if reporter is None:
        return None
    summary = reporter.summary()
    if not isinstance(summary, dict):
        return None
    return summary


def _build_instance_generator(
    app_config: AppConfig, *, seed_override: int | None = None
) -> InstanceGenerator:
    if seed_override is not None:
        seed_value: int | None = seed_override
    else:
        seed_value = None
        if app_config.seed is not None:
            seed_value = SeedManager(seed=app_config.seed).normalized_seed

    p_none = app_config.p_none if app_config.p_none is not None else 0.0
    gen_config = GenerationConfig(
        seed=seed_value,
        enum_policy=app_config.enum_policy,
        union_policy=app_config.union_policy,
        default_p_none=p_none,
        optional_p_none=p_none,
        time_anchor=app_config.now,
        field_policies=app_config.field_policies,
    )
    return InstanceGenerator(config=gen_config)


__all__ = ["register"]
