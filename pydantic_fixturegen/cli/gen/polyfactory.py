"""CLI command for exporting Polyfactory wrappers backed by fixturegen."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.logging import get_logger

from ..watch import gather_default_watch_paths, run_with_watch
from . import _common as cli_common
from ._common import JSON_ERRORS_OPTION, render_cli_error

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

OUT_OPTION = typer.Option(
    Path("polyfactory_factories.py"),
    "--out",
    "-o",
    help="Output python module path.",
)

STDOUT_OPTION = typer.Option(
    False,
    "--stdout",
    help="Print generated module to stdout instead of writing a file.",
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
    help="Seed embedded into the GenerationConfig template.",
)

MAX_DEPTH_OPTION = typer.Option(
    None,
    "--max-depth",
    min=1,
    help="Override recursion depth budget for the exported GenerationConfig.",
)

CYCLE_POLICY_OPTION = typer.Option(
    None,
    "--on-cycle",
    help="Cycle resolution policy (reuse, stub, null).",
)

RNG_MODE_OPTION = typer.Option(
    None,
    "--rng-mode",
    help="Random generator mode: 'portable' (default) or 'legacy'.",
)

WATCH_OPTION = typer.Option(
    False,
    "--watch",
    help="Watch the source file and regenerate factories on change.",
)

WATCH_DEBOUNCE_OPTION = typer.Option(
    0.5,
    "--watch-debounce",
    min=0.1,
    help="Debounce interval (seconds) for watch mode.",
)


def register(app: typer.Typer) -> None:
    @app.command("polyfactory")
    def gen_polyfactory(  # noqa: PLR0913 - CLI mirrors documentation
        target: str = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        stdout: bool = STDOUT_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
        seed: int | None = SEED_OPTION,
        max_depth: int | None = MAX_DEPTH_OPTION,
        cycle_policy: str | None = CYCLE_POLICY_OPTION,
        rng_mode: str | None = RNG_MODE_OPTION,
        watch: bool = WATCH_OPTION,
        watch_debounce: float = WATCH_DEBOUNCE_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
    ) -> None:
        logger = get_logger()

        try:
            __import__("polyfactory")
        except ModuleNotFoundError as exc:
            render_cli_error(
                DiscoveryError(
                    "Polyfactory is not installed. Install "
                    "'pydantic-fixturegen[polyfactory]' first."
                ),
                json_errors=json_errors,
            )
            raise typer.Exit(code=1) from exc

        target_path = Path(target)
        if not target_path.exists():
            render_cli_error(
                DiscoveryError(f"Target path '{target}' does not exist."),
                json_errors=json_errors,
            )
            return

        include_patterns = cli_common.split_patterns(include)
        exclude_patterns = cli_common.split_patterns(exclude)

        def invoke() -> None:
            try:
                source = _build_module_source(
                    target=target_path,
                    include=include_patterns or None,
                    exclude=exclude_patterns or None,
                    seed=seed,
                    max_depth=max_depth,
                    cycle_policy=cycle_policy,
                    rng_mode=rng_mode,
                )
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
                return

            if stdout:
                typer.echo(source)
                return
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(source, encoding="utf-8", newline="\n")
            logger.info(
                "Polyfactory module written",
                event="polyfactory_module_written",
                path=str(out),
            )

        if watch:
            watch_paths = gather_default_watch_paths(target_path, output=out)
            run_with_watch(lambda: invoke(), watch_paths, debounce=watch_debounce)
        else:
            invoke()


def _build_module_source(
    *,
    target: Path,
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
    seed: int | None,
    max_depth: int | None,
    cycle_policy: str | None,
    rng_mode: str | None,
) -> str:
    cli_common.clear_module_cache()
    discovery = cli_common.discover_models(
        target,
        include=include,
        exclude=exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))
    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    modules: dict[str, set[str]] = {}
    for model in discovery.models:
        modules.setdefault(model.module, set()).add(model.name)

    config_lines: list[str] = []
    if seed is not None:
        config_lines.append(f"    seed={seed},")
    if max_depth is not None:
        config_lines.append(f"    max_depth={max_depth},")
    if cycle_policy is not None:
        config_lines.append(f'    cycle_policy="{cycle_policy}",')
    if rng_mode is not None:
        config_lines.append(f'    rng_mode="{rng_mode}",')

    config_block = (
        "GenerationConfig(\n" + "\n".join(config_lines) + "\n)"
        if config_lines
        else "GenerationConfig()"
    )

    lines: list[str] = []
    lines.append('"""Polyfactory factories generated by pydantic-fixturegen."""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import dataclasses")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from polyfactory.factories.pydantic_factory import ModelFactory")
    lines.append(
        "from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator"
    )
    lines.append("")

    for module_name in sorted(modules):
        class_names = ", ".join(sorted(modules[module_name]))
        lines.append(f"from {module_name} import {class_names}")
    lines.append("")
    lines.append(f"_GENERATION_CONFIG = {config_block}")
    lines.append("_GENERATOR = InstanceGenerator(config=_GENERATION_CONFIG)")
    lines.append("")
    lines.append("def seed_factories(seed: int | None = None) -> None:")
    lines.append('    """Reseed the shared generator used by the exported factories."""')
    lines.append("    global _GENERATOR")
    lines.append("    config = dataclasses.replace(_GENERATION_CONFIG)")
    lines.append("    config.seed = seed")
    lines.append("    _GENERATOR = InstanceGenerator(config=config)")
    lines.append("")
    lines.append("def _build_instance(model: type[Any]) -> Any:")
    lines.append("    instance = _GENERATOR.generate_one(model)")
    lines.append("    if instance is None:")
    lines.append(
        "        raise RuntimeError(f\"pydantic-fixturegen could not build {model.__name__}.\")"
    )
    lines.append("    return instance")
    lines.append("")

    exported_names: list[str] = ["seed_factories"]
    for model in discovery.models:
        factory_name = f"{model.name}Factory"
        exported_names.append(factory_name)
        lines.append(f"class {factory_name}(ModelFactory[{model.name}]):")
        lines.append(f"    __model__ = {model.name}")
        lines.append("    __check_model__ = False")
        lines.append("    __set_as_default_factory_for_type__ = True")
        lines.append("")
        lines.append("    @classmethod")
        lines.append(
            "    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> "
            f"{model.name}:"
        )
        lines.append("        if kwargs:")
        lines.append(
            "            return super().build("
            "factory_use_construct=factory_use_construct, **kwargs)"
        )
        lines.append("        return _build_instance(cls.__model__)")
        lines.append("")

    lines.append(f"__all__ = {sorted(exported_names)!r}")
    lines.append("")
    return "\n".join(lines)


__all__ = ["register"]
