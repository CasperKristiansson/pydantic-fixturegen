"""Snapshot assertion helpers for pytest and other test frameworks."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic_fixturegen.api import generate_fixtures, generate_json, generate_schema
from pydantic_fixturegen.cli.diff import (
    FixturesDiffOptions,
    JsonDiffOptions,
    SchemaDiffOptions,
    _execute_diff,
)

__all__ = [
    "FixturesSnapshotConfig",
    "JsonSnapshotConfig",
    "SchemaSnapshotConfig",
    "SnapshotAssertionError",
    "SnapshotRunner",
    "SnapshotUpdateMode",
]


class SnapshotAssertionError(AssertionError):
    """Raised when snapshot comparison fails."""


class SnapshotUpdateMode(Enum):
    """Control how the snapshot helper reacts to drift."""

    FAIL = "fail"
    UPDATE = "update"

    @classmethod
    def coerce(cls, value: SnapshotUpdateMode | str | None) -> SnapshotUpdateMode:
        if isinstance(value, SnapshotUpdateMode):
            return value
        if value is None:
            return cls.FAIL
        normalized = value.strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Unsupported snapshot update mode: {value!r}")

    @classmethod
    def from_env(cls, env_var: str = "PFG_SNAPSHOT_UPDATE") -> SnapshotUpdateMode:
        return cls.coerce(os.getenv(env_var))


@dataclass(slots=True)
class JsonSnapshotConfig:
    """Configuration describing a JSON snapshot artifact."""

    out: Path
    count: int = 1
    jsonl: bool = False
    indent: int | None = None
    use_orjson: bool | None = None
    shard_size: int | None = None


@dataclass(slots=True)
class FixturesSnapshotConfig:
    """Configuration describing a pytest fixtures snapshot artifact."""

    out: Path
    style: str | None = None
    scope: str | None = None
    cases: int = 1
    return_type: str | None = None


@dataclass(slots=True)
class SchemaSnapshotConfig:
    """Configuration describing a schema snapshot artifact."""

    out: Path
    indent: int | None = None


@dataclass(slots=True)
class SnapshotRunner:
    """Execute snapshot comparisons against deterministic artifacts."""

    timeout: float = 5.0
    memory_limit_mb: int = 256
    ast_mode: bool = False
    hybrid_mode: bool = False
    update_mode: SnapshotUpdateMode = SnapshotUpdateMode.FAIL

    def assert_artifacts(
        self,
        target: str | Path,
        *,
        json: JsonSnapshotConfig | None = None,
        fixtures: FixturesSnapshotConfig | None = None,
        schema: SchemaSnapshotConfig | None = None,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
        seed: int | None = None,
        p_none: float | None = None,
        now: str | None = None,
        preset: str | None = None,
        profile: str | None = None,
        freeze_seeds: bool = False,
        freeze_seeds_file: str | Path | None = None,
        update: SnapshotUpdateMode | str | None = None,
    ) -> None:
        """Compare regenerated artifacts to snapshots or update when configured."""

        if json is None and fixtures is None and schema is None:
            raise ValueError("Provide at least one artifact configuration (json/fixtures/schema).")

        effective_mode = (
            SnapshotUpdateMode.coerce(update) if update is not None else self.update_mode
        )
        include_patterns = _normalize_patterns(include)
        exclude_patterns = _normalize_patterns(exclude)

        json_opts = _build_json_options(json)
        fixtures_opts = _build_fixtures_options(fixtures)
        schema_opts = _build_schema_options(schema)

        reports = _execute_diff(
            target=str(target),
            include=include_patterns,
            exclude=exclude_patterns,
            ast_mode=self.ast_mode,
            hybrid_mode=self.hybrid_mode,
            timeout=self.timeout,
            memory_limit_mb=self.memory_limit_mb,
            seed_override=seed,
            p_none_override=p_none,
            json_options=json_opts,
            fixtures_options=fixtures_opts,
            schema_options=schema_opts,
            freeze_seeds=freeze_seeds,
            freeze_seeds_file=Path(freeze_seeds_file) if freeze_seeds_file else None,
            preset=preset,
            profile=profile,
            now_override=now,
        )

        if not any(report.changed for report in reports):
            return

        if effective_mode is SnapshotUpdateMode.UPDATE:
            self._update_artifacts(
                target=Path(target),
                json=json,
                fixtures=fixtures,
                schema=schema,
                include=include,
                exclude=exclude,
                seed=seed,
                p_none=p_none,
                now=now,
                preset=preset,
                profile=profile,
                freeze_seeds=freeze_seeds,
                freeze_seeds_file=freeze_seeds_file,
            )
            reports = _execute_diff(
                target=str(target),
                include=include_patterns,
                exclude=exclude_patterns,
                ast_mode=self.ast_mode,
                hybrid_mode=self.hybrid_mode,
                timeout=self.timeout,
                memory_limit_mb=self.memory_limit_mb,
                seed_override=seed,
                p_none_override=p_none,
                json_options=json_opts,
                fixtures_options=fixtures_opts,
                schema_options=schema_opts,
                freeze_seeds=freeze_seeds,
                freeze_seeds_file=Path(freeze_seeds_file) if freeze_seeds_file else None,
                preset=preset,
                profile=profile,
                now_override=now,
            )
            if not any(report.changed for report in reports):
                return

        message = _format_failure_message(reports, effective_mode)
        raise SnapshotAssertionError(message)

    def _update_artifacts(
        self,
        *,
        target: Path,
        json: JsonSnapshotConfig | None,
        fixtures: FixturesSnapshotConfig | None,
        schema: SchemaSnapshotConfig | None,
        include: Sequence[str] | None,
        exclude: Sequence[str] | None,
        seed: int | None,
        p_none: float | None,
        now: str | None,
        preset: str | None,
        profile: str | None = None,
        freeze_seeds: bool,
        freeze_seeds_file: str | Path | None,
    ) -> None:
        include_seq = tuple(include) if include is not None else None
        exclude_seq = tuple(exclude) if exclude is not None else None

        if json and json.out:
            generate_json(
                target=str(target),
                out=json.out,
                count=json.count,
                jsonl=json.jsonl,
                indent=json.indent,
                use_orjson=json.use_orjson,
                shard_size=json.shard_size,
                include=include_seq,
                exclude=exclude_seq,
                seed=seed,
                now=now,
                freeze_seeds=freeze_seeds,
                freeze_seeds_file=freeze_seeds_file,
                preset=preset,
                profile=profile,
            )

        if fixtures and fixtures.out:
            generate_fixtures(
                target=str(target),
                out=fixtures.out,
                style=fixtures.style,
                scope=fixtures.scope,
                cases=fixtures.cases,
                return_type=fixtures.return_type,
                seed=seed,
                now=now,
                p_none=p_none,
                include=include_seq,
                exclude=exclude_seq,
                freeze_seeds=freeze_seeds,
                freeze_seeds_file=freeze_seeds_file,
                preset=preset,
                profile=profile,
            )

        if schema and schema.out:
            generate_schema(
                target=str(target),
                out=schema.out,
                indent=schema.indent,
                include=include_seq,
                exclude=exclude_seq,
                profile=profile,
            )


def _normalize_patterns(patterns: Sequence[str] | None) -> str | None:
    if patterns is None:
        return None
    cleaned = [pattern.strip() for pattern in patterns if pattern.strip()]
    return ",".join(cleaned) if cleaned else None


def _build_json_options(config: JsonSnapshotConfig | None) -> JsonDiffOptions:
    if config is None:
        return JsonDiffOptions(
            out=None,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
        )
    return JsonDiffOptions(
        out=config.out,
        count=config.count,
        jsonl=config.jsonl,
        indent=config.indent,
        use_orjson=config.use_orjson,
        shard_size=config.shard_size,
    )


def _build_fixtures_options(config: FixturesSnapshotConfig | None) -> FixturesDiffOptions:
    if config is None:
        return FixturesDiffOptions(
            out=None,
            style=None,
            scope=None,
            cases=1,
            return_type=None,
        )
    return FixturesDiffOptions(
        out=config.out,
        style=config.style,
        scope=config.scope,
        cases=config.cases,
        return_type=config.return_type,
    )


def _build_schema_options(config: SchemaSnapshotConfig | None) -> SchemaDiffOptions:
    if config is None:
        return SchemaDiffOptions(out=None, indent=None)
    return SchemaDiffOptions(out=config.out, indent=config.indent)


def _format_failure_message(
    reports: Iterable[Any],
    mode: SnapshotUpdateMode,
) -> str:
    blocks: list[str] = []
    for report in reports:
        if not getattr(report, "changed", False):
            continue
        header = f"{report.kind} mismatch for {report.target}"
        details: list[str] = []
        details.extend(report.messages)
        for path, diff_text in report.diff_outputs:
            formatted = diff_text.rstrip("\n")
            details.append(f"Diff for {path}:\n{formatted}")
        if report.summary:
            details.append(report.summary)
        blocks.append("\n".join([header] + details))

    if not blocks:
        message = "Artifacts differ but no additional detail was provided."
    else:
        message = "\n\n".join(blocks)

    if mode is SnapshotUpdateMode.FAIL:
        message = (
            f"{message}\n\n"
            "Run again with update='update', set PFG_SNAPSHOT_UPDATE=update, "
            "or pass --pfg-update-snapshots=update to refresh stored snapshots."
        )
    else:
        message = f"{message}\n\nSnapshot update attempted but differences remain."
    return message
