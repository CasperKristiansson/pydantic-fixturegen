"""CLI command for emitting Hypothesis strategy stubs."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, PFGError

from ...logging import get_logger
from ..watch import gather_default_watch_paths, run_with_watch
from . import _common as cli_common
from ._common import JSON_ERRORS_OPTION, render_cli_error

TARGET_ARGUMENT = typer.Argument(
    ...,
    help="Path to a Python module containing Pydantic models.",
)

OUT_OPTION = typer.Option(
    Path("strategies.py"),
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
    help="Seed override applied to GenerationConfig before exporting strategies.",
)

PROFILE_OPTION = typer.Option(
    "typical",
    "--strategy-profile",
    help="Strategy profile to use (typical, edge, adversarial).",
    case_sensitive=False,
)

MAX_DEPTH_OPTION = typer.Option(
    None,
    "--max-depth",
    min=1,
    help="Override recursion depth budget for strategy generation.",
)

CYCLE_POLICY_OPTION = typer.Option(
    None,
    "--on-cycle",
    help="Cycle resolution policy (reuse, stub, null).",
)

RNG_MODE_OPTION = typer.Option(
    None,
    "--rng-mode",
    help="RNG mode to apply to the exported GenerationConfig (portable or legacy).",
)

WATCH_OPTION = typer.Option(
    False,
    "--watch",
    help="Watch the source file and regenerate strategies on change.",
)

WATCH_DEBOUNCE_OPTION = typer.Option(
    0.5,
    "--watch-debounce",
    min=0.1,
    help="Debounce interval (seconds) for watch mode.",
)


def register(app: typer.Typer) -> None:
    @app.command("strategies")
    def gen_strategies(  # noqa: PLR0913 - CLI mirrors documentation
        target: str = TARGET_ARGUMENT,
        out: Path = OUT_OPTION,
        stdout: bool = STDOUT_OPTION,
        include: str | None = INCLUDE_OPTION,
        exclude: str | None = EXCLUDE_OPTION,
        seed: int | None = SEED_OPTION,
        strategy_profile: str = PROFILE_OPTION,
        max_depth: int | None = MAX_DEPTH_OPTION,
        cycle_policy: str | None = CYCLE_POLICY_OPTION,
        rng_mode: str | None = RNG_MODE_OPTION,
        watch: bool = WATCH_OPTION,
        watch_debounce: float = WATCH_DEBOUNCE_OPTION,
        json_errors: bool = JSON_ERRORS_OPTION,
    ) -> None:
        logger = get_logger()

        strategy_profile = strategy_profile.lower()
        if strategy_profile not in {"typical", "edge", "adversarial"}:
            raise ConfigError("strategy-profile must be one of: typical, edge, adversarial")

        target_path = Path(target)
        if not target_path.exists():
            render_cli_error(
                DiscoveryError(f"Target path '{target}' does not exist."),
                json_errors=json_errors,
            )
            return

        watch_paths: list[Path] | None = None
        if watch:
            watch_paths = gather_default_watch_paths(target_path, output=out)

        def invoke() -> None:
            try:
                module_source = _build_source(
                    target=target_path,
                    include=include,
                    exclude=exclude,
                    seed=seed,
                    strategy_profile=strategy_profile,
                    max_depth=max_depth,
                    cycle_policy=cycle_policy,
                    rng_mode=rng_mode,
                )
            except PFGError as exc:
                render_cli_error(exc, json_errors=json_errors)
                return

            if stdout:
                typer.echo(module_source)
                return
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(module_source, encoding="utf-8", newline="\n")
            logger.info(
                "Strategies module written",
                event="strategies_written",
                path=str(out),
            )

        if watch and watch_paths:
            run_with_watch(lambda: invoke(), watch_paths, debounce=watch_debounce)
        else:
            invoke()


def _build_source(
    *,
    target: Path,
    include: str | None,
    exclude: str | None,
    seed: int | None,
    strategy_profile: str,
    max_depth: int | None,
    cycle_policy: str | None,
    rng_mode: str | None,
) -> str:
    include_patterns = cli_common.split_patterns(include)
    exclude_patterns = cli_common.split_patterns(exclude)

    discovery = cli_common.discover_models(
        target,
        include=include_patterns or None,
        exclude=exclude_patterns or None,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))
    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    modules: dict[str, list[str]] = {}
    for model in discovery.models:
        modules.setdefault(model.module, []).append(model.name)

    config_lines = []
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
    lines.append('"""Hypothesis strategies generated by pydantic-fixturegen."""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from pydantic_fixturegen.core.generate import GenerationConfig")
    lines.append("from pydantic_fixturegen.hypothesis import strategy_for")

    for module_name, class_names in sorted(modules.items()):
        joined = ", ".join(sorted(class_names))
        lines.append(f"from {module_name} import {joined}")

    lines.append("")
    lines.append(f"_GENERATION_CONFIG = {config_block}")
    lines.append("")

    exported: list[str] = []
    for model in discovery.models:
        var_name = _var_name(model.module, model.name)
        exported.append(var_name)
        lines.append(
            f"{var_name} = strategy_for(\n"
            f"    {model.name},\n"
            f"    generation_config=_GENERATION_CONFIG,\n"
            f'    profile="{strategy_profile}",\n'
            f")"
        )
        lines.append("")

    lines.append(f"__all__ = {exported!r}")
    lines.append("")
    return "\n".join(lines)


def _var_name(module: str, model_name: str) -> str:
    suffix = module.split(".")[-1]
    base = f"{suffix}_{model_name}_strategy"
    return re.sub(r"[^0-9A-Za-z_]", "_", base).lower()


__all__ = ["register"]
