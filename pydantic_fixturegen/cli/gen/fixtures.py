"""CLI command for emitting pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.core.config import load_config
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures
from ._common import clear_module_cache, discover_models, load_model_class, split_patterns


STYLE_CHOICES = ["functions", "factory", "class"]
SCOPE_CHOICES = ["function", "module", "session"]
RETURN_CHOICES = ["model", "dict"]


def register(app: typer.Typer) -> None:
    @app.command("fixtures")
    def gen_fixtures(  # noqa: PLR0915 - CLI surface mirrors documented parameters
        target: str = typer.Argument(
            ...,
            help="Path to a Python module containing Pydantic models.",
        ),
        out: Path = typer.Option(
            ...,
            "--out",
            "-o",
            help="Output file path for generated fixtures.",
        ),
        style: str | None = typer.Option(
            None,
            "--style",
            help="Fixture style (functions, factory, class).",
        ),
        scope: str | None = typer.Option(
            None,
            "--scope",
            help="Fixture scope (function, module, session).",
        ),
        cases: int = typer.Option(
            1,
            "--cases",
            min=1,
            help="Number of cases per fixture (parametrization size).",
        ),
        return_type: str | None = typer.Option(
            None,
            "--return-type",
            help="Return type: model or dict.",
        ),
        seed: int | None = typer.Option(
            None,
            "--seed",
            help="Seed override for deterministic generation.",
        ),
        p_none: float | None = typer.Option(
            None,
            "--p-none",
            min=0.0,
            max=1.0,
            help="Probability of None for optional fields.",
        ),
        include: str | None = typer.Option(
            None,
            "--include",
            "-i",
            help="Comma-separated pattern(s) of fully-qualified model names to include.",
        ),
        exclude: str | None = typer.Option(
            None,
            "--exclude",
            "-e",
            help="Comma-separated pattern(s) of fully-qualified model names to exclude.",
        ),
    ) -> None:
        path = Path(target)
        if not path.exists():
            raise typer.BadParameter(f"Target path '{target}' does not exist.", param_hint="target")
        if not path.is_file():
            raise typer.BadParameter("Target must be a Python module file.", param_hint="target")

        clear_module_cache()

        cli_overrides: dict[str, Any] = {}
        if seed is not None:
            cli_overrides["seed"] = seed
        if p_none is not None:
            cli_overrides["p_none"] = p_none
        emitter_overrides: dict[str, Any] = {}
        if style is not None:
            emitter_overrides["style"] = style.lower()
        if scope is not None:
            emitter_overrides["scope"] = scope.lower()
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
            for error in discovery.errors:
                typer.secho(error, err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)

        for warning in discovery.warnings:
            if warning.strip():
                typer.secho(warning.strip(), err=True, fg=typer.colors.YELLOW)

        if not discovery.models:
            typer.secho("No models discovered.", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)

        try:
            model_classes = [load_model_class(model) for model in discovery.models]
        except RuntimeError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

        seed_value: int | None = None
        if app_config.seed is not None:
            seed_value = SeedManager(seed=app_config.seed).normalized_seed

        style_value = app_config.emitters.pytest.style
        if style is not None:
            style_lower = style.lower()
            if style_lower not in STYLE_CHOICES:
                raise typer.BadParameter(f"Invalid style '{style}'.", param_hint="--style")
            style_value = style_lower

        scope_value = app_config.emitters.pytest.scope
        if scope is not None:
            scope_lower = scope.lower()
            if scope_lower not in SCOPE_CHOICES:
                raise typer.BadParameter(f"Invalid scope '{scope}'.", param_hint="--scope")
            scope_value = scope_lower

        if return_type is not None:
            return_type_value = return_type.lower()
            if return_type_value not in RETURN_CHOICES:
                raise typer.BadParameter(
                    f"Invalid return type '{return_type}'.",
                    param_hint="--return-type",
                )
        else:
            return_type_value = "model"

        pytest_config = PytestEmitConfig(
            scope=scope_value,
            style=style_value,
            return_type=return_type_value,
            cases=cases,
            seed=seed_value,
            optional_p_none=app_config.p_none,
        )

        try:
            result = emit_pytest_fixtures(
                model_classes,
                output_path=out,
                config=pytest_config,
            )
        except Exception as exc:  # pragma: no cover - ensure CLI surfaces error
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

        message = str(out)
        if result.skipped:
            message += " (unchanged)"
        typer.echo(message)


__all__ = ["register"]
