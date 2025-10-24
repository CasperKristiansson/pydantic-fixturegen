"""CLI command for generating JSON/JSONL samples."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from pydantic_fixturegen.core.config import AppConfig, load_config
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.emitters.json_out import emit_json_samples
from ._common import clear_module_cache, discover_models, load_model_class, split_patterns


def register(app: typer.Typer) -> None:
    @app.command("json")
    def gen_json(  # noqa: PLR0913 - CLI surface mirrors documented parameters
        target: str = typer.Argument(
            ...,
            help="Path to a Python module containing Pydantic models.",
        ),
        out: Path = typer.Option(
            ...,
            "--out",
            "-o",
            help="Output file path (single file or shard prefix).",
        ),
        count: int = typer.Option(
            1,
            "--n",
            "-n",
            min=1,
            help="Number of samples to generate.",
        ),
        jsonl: bool = typer.Option(
            False,
            "--jsonl",
            help="Emit newline-delimited JSON instead of a JSON array.",
        ),
        indent: int | None = typer.Option(
            None,
            "--indent",
            min=0,
            help="Indentation level for JSON output (overrides config).",
        ),
        use_orjson: bool | None = typer.Option(
            None,
            "--orjson/--no-orjson",
            help="Toggle orjson serialization (overrides config).",
        ),
        shard_size: int | None = typer.Option(
            None,
            "--shard-size",
            min=1,
            help="Maximum number of records per shard (JSONL or JSON).",
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
        seed: int | None = typer.Option(
            None,
            "--seed",
            help="Seed override for deterministic generation.",
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

        if len(discovery.models) > 1:
            names = ", ".join(model.qualname for model in discovery.models)
            typer.secho(
                f"Multiple models discovered ({names}). Use --include/--exclude to narrow selection.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        target_model = discovery.models[0]

        try:
            model_cls = load_model_class(target_model)
        except RuntimeError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

        generator = _build_instance_generator(app_config)

        def sample_factory() -> BaseModel:
            instance = generator.generate_one(model_cls)
            if instance is None:
                raise RuntimeError(f"Failed to generate instance for {target_model.qualname}.")
            return instance

        indent_value = indent if indent is not None else app_config.json.indent
        use_orjson_value = use_orjson if use_orjson is not None else app_config.json.orjson

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
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

        for emitted_path in paths:
            typer.echo(str(emitted_path))


def _build_instance_generator(app_config: AppConfig) -> InstanceGenerator:
    seed_value: int | None = None
    if app_config.seed is not None:
        seed_value = SeedManager(seed=app_config.seed).normalized_seed

    p_none = app_config.p_none if app_config.p_none is not None else 0.0
    gen_config = GenerationConfig(
        seed=seed_value,
        enum_policy=app_config.enum_policy,
        union_policy=app_config.union_policy,
        default_p_none=p_none,
        optional_p_none=p_none,
    )
    return InstanceGenerator(config=gen_config)
