"""CLI helpers for verifying and refreshing stored snapshots."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.cli.diff import (
    AST_OPTION,
    EXCLUDE_OPTION,
    FIXTURES_CASES_OPTION,
    FIXTURES_OUT_OPTION,
    FIXTURES_RETURN_OPTION,
    FIXTURES_SCOPE_OPTION,
    FIXTURES_STYLE_OPTION,
    FREEZE_FILE_OPTION,
    FREEZE_SEEDS_OPTION,
    HYBRID_OPTION,
    INCLUDE_OPTION,
    JSON_COUNT_OPTION,
    JSON_INDENT_OPTION,
    JSON_JSONL_OPTION,
    JSON_ORJSON_OPTION,
    JSON_OUT_OPTION,
    JSON_SHARD_OPTION,
    LINK_OPTION,
    MEMORY_LIMIT_OPTION,
    PATH_ARGUMENT,
    PNONE_OPTION,
    PRESET_OPTION,
    PROFILE_OPTION,
    RESPECT_VALIDATORS_OPTION,
    SCHEMA_INDENT_OPTION,
    SCHEMA_OUT_OPTION,
    SEED_OPTION,
    TIMEOUT_OPTION,
    VALIDATOR_MAX_RETRIES_OPTION,
)
from pydantic_fixturegen.cli.gen._common import (
    NOW_OPTION,
    RNG_MODE_OPTION,
    render_cli_error,
    split_patterns,
)
from pydantic_fixturegen.core.errors import PFGError
from pydantic_fixturegen.testing import (
    FixturesSnapshotConfig,
    JsonSnapshotConfig,
    SchemaSnapshotConfig,
    SnapshotAssertionError,
    SnapshotResult,
    SnapshotRunner,
    SnapshotUpdateMode,
)

app = typer.Typer(help="Manage snapshot artifacts.")


@app.command("verify")
def verify_snapshots(  # noqa: PLR0913
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    seed: int | None = SEED_OPTION,
    p_none: float | None = PNONE_OPTION,
    now: str | None = NOW_OPTION,
    preset: str | None = PRESET_OPTION,
    profile: str | None = PROFILE_OPTION,
    freeze_seeds: bool = FREEZE_SEEDS_OPTION,
    freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
    json_count: int = JSON_COUNT_OPTION,
    json_jsonl: bool = JSON_JSONL_OPTION,
    json_indent: int | None = JSON_INDENT_OPTION,
    json_orjson: bool | None = JSON_ORJSON_OPTION,
    json_shard_size: int | None = JSON_SHARD_OPTION,
    fixtures_out: Path | None = FIXTURES_OUT_OPTION,
    fixtures_style: str | None = FIXTURES_STYLE_OPTION,
    fixtures_scope: str | None = FIXTURES_SCOPE_OPTION,
    fixtures_cases: int = FIXTURES_CASES_OPTION,
    fixtures_return_type: str | None = FIXTURES_RETURN_OPTION,
    schema_out: Path | None = SCHEMA_OUT_OPTION,
    schema_indent: int | None = SCHEMA_INDENT_OPTION,
    respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
    validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
    links: list[str] | None = LINK_OPTION,
    rng_mode: str | None = RNG_MODE_OPTION,
) -> None:
    """Verify that stored snapshots match freshly generated artifacts."""

    _run_snapshot_command(
        path=path,
        include=include,
        exclude=exclude,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
        seed=seed,
        p_none=p_none,
        now=now,
        preset=preset,
        profile=profile,
        freeze_seeds=freeze_seeds,
        freeze_seeds_file=freeze_seeds_file,
        json_config=_build_json_config(
            json_out,
            count=json_count,
            jsonl=json_jsonl,
            indent=json_indent,
            use_orjson=json_orjson,
            shard_size=json_shard_size,
        ),
        fixtures_config=_build_fixtures_config(
            fixtures_out,
            style=fixtures_style,
            scope=fixtures_scope,
            cases=fixtures_cases,
            return_type=fixtures_return_type,
        ),
        schema_config=_build_schema_config(schema_out, indent=schema_indent),
        update_mode=SnapshotUpdateMode.FAIL,
        respect_validators=respect_validators,
        validator_max_retries=validator_max_retries,
        links=links,
        rng_mode=rng_mode,
        success_message="Snapshots verified.",
    )


@app.command("write")
def write_snapshots(  # noqa: PLR0913
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    seed: int | None = SEED_OPTION,
    p_none: float | None = PNONE_OPTION,
    now: str | None = NOW_OPTION,
    preset: str | None = PRESET_OPTION,
    profile: str | None = PROFILE_OPTION,
    freeze_seeds: bool = FREEZE_SEEDS_OPTION,
    freeze_seeds_file: Path | None = FREEZE_FILE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
    json_count: int = JSON_COUNT_OPTION,
    json_jsonl: bool = JSON_JSONL_OPTION,
    json_indent: int | None = JSON_INDENT_OPTION,
    json_orjson: bool | None = JSON_ORJSON_OPTION,
    json_shard_size: int | None = JSON_SHARD_OPTION,
    fixtures_out: Path | None = FIXTURES_OUT_OPTION,
    fixtures_style: str | None = FIXTURES_STYLE_OPTION,
    fixtures_scope: str | None = FIXTURES_SCOPE_OPTION,
    fixtures_cases: int = FIXTURES_CASES_OPTION,
    fixtures_return_type: str | None = FIXTURES_RETURN_OPTION,
    schema_out: Path | None = SCHEMA_OUT_OPTION,
    schema_indent: int | None = SCHEMA_INDENT_OPTION,
    respect_validators: bool | None = RESPECT_VALIDATORS_OPTION,
    validator_max_retries: int | None = VALIDATOR_MAX_RETRIES_OPTION,
    links: list[str] | None = LINK_OPTION,
    rng_mode: str | None = RNG_MODE_OPTION,
) -> None:
    """Regenerate snapshots in place."""

    _run_snapshot_command(
        path=path,
        include=include,
        exclude=exclude,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
        seed=seed,
        p_none=p_none,
        now=now,
        preset=preset,
        profile=profile,
        freeze_seeds=freeze_seeds,
        freeze_seeds_file=freeze_seeds_file,
        json_config=_build_json_config(
            json_out,
            count=json_count,
            jsonl=json_jsonl,
            indent=json_indent,
            use_orjson=json_orjson,
            shard_size=json_shard_size,
        ),
        fixtures_config=_build_fixtures_config(
            fixtures_out,
            style=fixtures_style,
            scope=fixtures_scope,
            cases=fixtures_cases,
            return_type=fixtures_return_type,
        ),
        schema_config=_build_schema_config(schema_out, indent=schema_indent),
        update_mode=SnapshotUpdateMode.UPDATE,
        respect_validators=respect_validators,
        validator_max_retries=validator_max_retries,
        links=links,
        rng_mode=rng_mode,
        success_message="Snapshots refreshed.",
    )


app.command("update")(write_snapshots)


def _run_snapshot_command(
    *,
    path: str,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
    seed: int | None,
    p_none: float | None,
    now: str | None,
    preset: str | None,
    profile: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    json_config: JsonSnapshotConfig | None,
    fixtures_config: FixturesSnapshotConfig | None,
    schema_config: SchemaSnapshotConfig | None,
    update_mode: SnapshotUpdateMode,
    respect_validators: bool | None,
    validator_max_retries: int | None,
    links: list[str] | None,
    rng_mode: str | None,
    success_message: str,
) -> None:
    if json_config is None and fixtures_config is None and schema_config is None:
        raise typer.BadParameter("Provide at least one of --json-out/--fixtures-out/--schema-out.")

    runner = SnapshotRunner(
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        update_mode=update_mode,
    )
    include_patterns = tuple(split_patterns(include)) or None
    exclude_patterns = tuple(split_patterns(exclude)) or None
    freeze_file = freeze_seeds_file if freeze_seeds_file is None else Path(freeze_seeds_file)

    try:
        result = runner.assert_artifacts(
            path,
            json=json_config,
            fixtures=fixtures_config,
            schema=schema_config,
            include=include_patterns,
            exclude=exclude_patterns,
            seed=seed,
            p_none=p_none,
            now=now,
            preset=preset,
            profile=profile,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=freeze_file,
            update=update_mode,
            respect_validators=respect_validators,
            validator_max_retries=validator_max_retries,
            links=links or None,
            rng_mode=rng_mode,
        )
    except SnapshotAssertionError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except PFGError as exc:
        render_cli_error(exc, json_errors=False, exit_app=False)
        raise typer.Exit(code=1) from exc

    _echo_result(result, success_message, update_mode)


def _echo_result(result: SnapshotResult, success_message: str, mode: SnapshotUpdateMode) -> None:
    if mode is SnapshotUpdateMode.UPDATE and result.updated:
        typer.secho(success_message, fg=typer.colors.GREEN)
    elif mode is SnapshotUpdateMode.UPDATE:
        typer.secho("Snapshots already up to date.", fg=typer.colors.GREEN)
    else:
        typer.secho(success_message, fg=typer.colors.GREEN)


def _build_json_config(
    path: Path | None,
    *,
    count: int,
    jsonl: bool,
    indent: int | None,
    use_orjson: bool | None,
    shard_size: int | None,
) -> JsonSnapshotConfig | None:
    if path is None:
        return None
    return JsonSnapshotConfig(
        out=path,
        count=count,
        jsonl=jsonl,
        indent=indent,
        use_orjson=use_orjson,
        shard_size=shard_size,
    )


def _build_fixtures_config(
    path: Path | None,
    *,
    style: str | None,
    scope: str | None,
    cases: int,
    return_type: str | None,
) -> FixturesSnapshotConfig | None:
    if path is None:
        return None
    return FixturesSnapshotConfig(
        out=path,
        style=style,
        scope=scope,
        cases=cases,
        return_type=return_type,
    )


def _build_schema_config(
    path: Path | None,
    *,
    indent: int | None,
) -> SchemaSnapshotConfig | None:
    if path is None:
        return None
    return SchemaSnapshotConfig(out=path, indent=indent)


__all__ = ["app"]
