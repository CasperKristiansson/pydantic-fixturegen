"""Public Python API for pydantic-fixturegen."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pydantic_fixturegen.core.path_template import OutputTemplate

from ._runtime import (
    generate_fixtures_artifacts,
    generate_json_artifacts,
    generate_schema_artifacts,
)
from .models import FixturesGenerationResult, JsonGenerationResult, SchemaGenerationResult

__all__ = [
    "FixturesGenerationResult",
    "JsonGenerationResult",
    "SchemaGenerationResult",
    "generate_fixtures",
    "generate_json",
    "generate_schema",
]


def generate_json(
    target: str | Path,
    *,
    out: str | Path,
    count: int = 1,
    jsonl: bool = False,
    indent: int | None = None,
    use_orjson: bool | None = None,
    shard_size: int | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    seed: int | None = None,
    now: str | None = None,
    freeze_seeds: bool = False,
    freeze_seeds_file: str | Path | None = None,
    preset: str | None = None,
) -> JsonGenerationResult:
    """Generate JSON artifacts for a single Pydantic model.

    Parameters mirror the ``pfg gen json`` CLI command.
    """

    template = OutputTemplate(str(out))
    freeze_path = Path(freeze_seeds_file) if freeze_seeds_file is not None else None

    return generate_json_artifacts(
        target=target,
        output_template=template,
        count=count,
        jsonl=jsonl,
        indent=indent,
        use_orjson=use_orjson,
        shard_size=shard_size,
        include=_normalize_sequence(include),
        exclude=_normalize_sequence(exclude),
        seed=seed,
        now=now,
        freeze_seeds=freeze_seeds,
        freeze_seeds_file=freeze_path,
        preset=preset,
    )


def generate_fixtures(
    target: str | Path,
    *,
    out: str | Path,
    style: str | None = None,
    scope: str | None = None,
    cases: int = 1,
    return_type: str | None = None,
    seed: int | None = None,
    now: str | None = None,
    p_none: float | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    freeze_seeds: bool = False,
    freeze_seeds_file: str | Path | None = None,
    preset: str | None = None,
) -> FixturesGenerationResult:
    """Emit pytest fixtures for discovered models.

    Returns a :class:`FixturesGenerationResult` describing the write outcome.
    """

    template = OutputTemplate(str(out))
    freeze_path = Path(freeze_seeds_file) if freeze_seeds_file is not None else None

    return generate_fixtures_artifacts(
        target=target,
        output_template=template,
        style=style,
        scope=scope,
        cases=cases,
        return_type=return_type,
        seed=seed,
        now=now,
        p_none=p_none,
        include=_normalize_sequence(include),
        exclude=_normalize_sequence(exclude),
        freeze_seeds=freeze_seeds,
        freeze_seeds_file=freeze_path,
        preset=preset,
    )


def generate_schema(
    target: str | Path,
    *,
    out: str | Path,
    indent: int | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> SchemaGenerationResult:
    """Emit JSON Schema for one or more models."""

    template = OutputTemplate(str(out))

    return generate_schema_artifacts(
        target=target,
        output_template=template,
        indent=indent,
        include=_normalize_sequence(include),
        exclude=_normalize_sequence(exclude),
    )


def _normalize_sequence(values: Sequence[str] | None) -> Sequence[str] | None:
    if values is None:
        return None
    return tuple(values)
