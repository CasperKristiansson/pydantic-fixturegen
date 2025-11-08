"""Data models for the public Python API."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pydantic_fixturegen.core.seed import RNGModeLiteral


@dataclass(slots=True)
class ConfigSnapshot:
    """Relevant configuration details captured during generation."""

    seed: int | str | None
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    time_anchor: _dt.datetime | None
    max_depth: int = 5
    cycle_policy: str = "reuse"
    rng_mode: RNGModeLiteral = "portable"


@dataclass(slots=True)
class JsonGenerationResult:
    """Result payload returned from :func:`pydantic_fixturegen.api.generate_json`."""

    paths: tuple[Path, ...]
    base_output: Path
    model: type[BaseModel] | None
    config: ConfigSnapshot
    constraint_summary: Mapping[str, Any] | None
    warnings: tuple[str, ...]
    delegated: bool
    type_annotation: Any | None = None
    type_label: str | None = None


@dataclass(slots=True)
class FixturesGenerationResult:
    """Result payload for pytest fixture emission."""

    path: Path | None
    base_output: Path
    models: tuple[type[BaseModel], ...]
    config: ConfigSnapshot
    metadata: Mapping[str, Any] | None
    warnings: tuple[str, ...]
    constraint_summary: Mapping[str, Any] | None
    skipped: bool
    delegated: bool
    style: str
    scope: str
    return_type: str
    cases: int


@dataclass(slots=True)
class SchemaGenerationResult:
    """Result payload for JSON Schema emission."""

    path: Path | None
    base_output: Path
    models: tuple[type[BaseModel], ...]
    config: ConfigSnapshot
    warnings: tuple[str, ...]
    delegated: bool


__all__ = [
    "ConfigSnapshot",
    "FixturesGenerationResult",
    "JsonGenerationResult",
    "SchemaGenerationResult",
]
