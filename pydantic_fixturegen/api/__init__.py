from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic_fixturegen.core.path_template import OutputTemplate

from ._runtime import (
    generate_dataset_artifacts,
    generate_fixtures_artifacts,
    generate_json_artifacts,
    generate_schema_artifacts,
)
from .anonymize import anonymize_from_rules, anonymize_payloads
from .models import (
    DatasetGenerationResult,
    FixturesGenerationResult,
    JsonGenerationResult,
    SchemaGenerationResult,
)

__all__ = [
    "DatasetGenerationResult",
    "FixturesGenerationResult",
    "JsonGenerationResult",
    "SchemaGenerationResult",
    "generate_dataset",
    "generate_fixtures",
    "generate_json",
    "generate_schema",
    "anonymize_payloads",
    "anonymize_from_rules",
]


def generate_json(
    target: str | Path | None,
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
    profile: str | None = None,
    type_annotation: Any | None = None,
    type_label: str | None = None,
) -> JsonGenerationResult:
    """Generate JSON artifacts for a single Pydantic model or ``TypeAdapter`` target.

    Parameters mirror the ``pfg gen json`` CLI command. When ``type_annotation`` is provided,
    ``target`` may be ``None`` and the annotation will be evaluated directly via a
    dynamically constructed adapter.
    """

    template = OutputTemplate(str(out))
    freeze_path = Path(freeze_seeds_file) if freeze_seeds_file is not None else None

    label_override = type_label
    if label_override is None and type_annotation is not None:
        label_override = repr(type_annotation)

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
        profile=profile,
        type_annotation=type_annotation,
        type_label=label_override,
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
    profile: str | None = None,
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
        profile=profile,
    )


def generate_schema(
    target: str | Path,
    *,
    out: str | Path,
    indent: int | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    profile: str | None = None,
) -> SchemaGenerationResult:
    """Emit JSON Schema for one or more models."""

    template = OutputTemplate(str(out))

    return generate_schema_artifacts(
        target=target,
        output_template=template,
        indent=indent,
        include=_normalize_sequence(include),
        exclude=_normalize_sequence(exclude),
        profile=profile,
    )


def _normalize_sequence(values: Sequence[str] | None) -> Sequence[str] | None:
    if values is None:
        return None
    return tuple(values)


def generate_dataset(
    target: str | Path,
    *,
    out: str | Path,
    count: int = 1,
    format: str = "csv",
    shard_size: int | None = None,
    compression: str | None = None,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    seed: int | None = None,
    now: str | None = None,
    freeze_seeds: bool = False,
    freeze_seeds_file: str | Path | None = None,
    preset: str | None = None,
    profile: str | None = None,
    respect_validators: bool | None = None,
    validator_max_retries: int | None = None,
    relations: Mapping[str, str] | None = None,
    max_depth: int | None = None,
    cycle_policy: str | None = None,
    rng_mode: str | None = None,
) -> DatasetGenerationResult:
    """Generate CSV/Parquet/Arrow datasets for a single Pydantic model."""

    template = OutputTemplate(str(out))
    freeze_path = Path(freeze_seeds_file) if freeze_seeds_file is not None else None

    return generate_dataset_artifacts(
        target=target,
        output_template=template,
        count=count,
        format=format,
        shard_size=shard_size,
        compression=compression,
        include=_normalize_sequence(include),
        exclude=_normalize_sequence(exclude),
        seed=seed,
        now=now,
        freeze_seeds=freeze_seeds,
        freeze_seeds_file=freeze_path,
        preset=preset,
        profile=profile,
        respect_validators=respect_validators,
        validator_max_retries=validator_max_retries,
        relations=relations,
        with_related=None,
        logger=None,
        max_depth=max_depth,
        cycle_policy=cycle_policy,
        rng_mode=rng_mode,
    )
