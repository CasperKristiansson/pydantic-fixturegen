"""CLI command for emitting pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.core.config import ConfigError, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, PFGError
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ._common import (
    JSON_ERRORS_OPTION,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)

STYLE_CHOICES = {"functions", "factory", "class"}
SCOPE_CHOICES = {"function", "module", "session"}
RETURN_CHOICES = {"model", "dict"}

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
    ) -> None:
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
            )
        except PFGError as exc:
            render_cli_error(exc, json_errors=json_errors)
        except ConfigError as exc:
            render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
        except Exception as exc:  # pragma: no cover - defensive
            render_cli_error(EmitError(str(exc)), json_errors=json_errors)


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
) -> None:
    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    style_value = style.lower() if style else None
    if style_value and style_value not in STYLE_CHOICES:
        raise DiscoveryError(f"Invalid style '{style}'.", details={"style": style})

    scope_value = scope.lower() if scope else None
    if scope_value and scope_value not in SCOPE_CHOICES:
        raise DiscoveryError(f"Invalid scope '{scope}'.", details={"scope": scope})

    return_type_value = return_type.lower() if return_type else None
    if return_type_value and return_type_value not in RETURN_CHOICES:
        raise DiscoveryError(
            f"Invalid return type '{return_type}'.",
            details={"return_type": return_type},
        )

    clear_module_cache()
    load_entrypoint_plugins()

    cli_overrides: dict[str, Any] = {}
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

    discovery = discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            typer.secho(warning.strip(), err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    try:
        model_classes = [load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:
        raise DiscoveryError(str(exc)) from exc

    seed_value: int | None = None
    if app_config.seed is not None:
        seed_value = SeedManager(seed=app_config.seed).normalized_seed

    style_final = style_value or app_config.emitters.pytest.style
    scope_final = scope_value or app_config.emitters.pytest.scope
    return_type_final = return_type_value or "model"

    pytest_config = PytestEmitConfig(
        scope=scope_final,
        style=style_final,
        return_type=return_type_final,
        cases=cases,
        seed=seed_value,
        optional_p_none=app_config.p_none,
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
        return

    try:
        result = emit_pytest_fixtures(
            model_classes,
            output_path=out,
            config=pytest_config,
        )
    except Exception as exc:
        raise EmitError(str(exc)) from exc

    message = str(out)
    if result.skipped:
        message += " (unchanged)"
    typer.echo(message)


__all__ = ["register"]
