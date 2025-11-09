"""Utilities for generating and verifying coverage manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_fixturegen.cli.doctor import (
    ModelReport,
    _run_doctor_analysis,
)
from pydantic_fixturegen.core.errors import EmitError
from pydantic_fixturegen.core.openapi import (
    dump_document,
    load_openapi_document,
    parse_route_value,
    select_openapi_schemas,
)
from pydantic_fixturegen.core.schema_ingest import SchemaIngester
from pydantic_fixturegen.core.seed_freeze import canonical_module_name

MANIFEST_VERSION = 1


@dataclass(slots=True)
class CoverageManifest:
    version: int
    generated_at: str
    target: str
    options: dict[str, Any]
    models: list[dict[str, Any]] = field(default_factory=list)
    gap_summary: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "target": self.target,
            "options": self.options,
            "models": self.models,
            "gap_summary": self.gap_summary,
        }

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.to_payload()
        payload.pop("generated_at", None)
        return payload

    @classmethod
    def from_payload(cls, data: Mapping[str, Any]) -> CoverageManifest:
        try:
            version = int(data.get("version", 0))
            generated_at = str(data.get("generated_at", ""))
            target = str(data.get("target", ""))
            options = dict(data.get("options", {}))
            models = list(data.get("models", []))
            gap_summary = dict(data.get("gap_summary", {}))
        except Exception as exc:  # pragma: no cover - defensive
            raise EmitError("Invalid coverage lockfile format.") from exc

        if version != MANIFEST_VERSION:
            raise EmitError(
                (
                    "Coverage lockfile version mismatch. "
                    f"Expected {MANIFEST_VERSION}, found {version}."
                ),
                details={"version": version},
            )

        return cls(
            version=version,
            generated_at=generated_at,
            target=target,
            options=options,
            models=models,
            gap_summary=gap_summary,
        )


def build_coverage_manifest(
    *,
    target: Path,
    include: str | None,
    exclude: str | None,
    schema: Path | None,
    openapi: Path | None,
    routes: Sequence[str] | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
) -> CoverageManifest:
    path, auto_include = _prepare_manifest_target(target, schema, openapi, routes)
    include_value: str | None = include
    if include_value and auto_include:
        include_value = f"{include_value},{','.join(auto_include)}"
    elif auto_include and not include_value:
        include_value = ",".join(auto_include)

    reports, gap_summary = _run_doctor_analysis(
        target=str(path),
        include=include_value,
        exclude=exclude,
        ast_mode=ast_mode,
        hybrid_mode=hybrid_mode,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )

    manifest_models = _serialize_models(reports)
    manifest_gap_summary = _serialize_gap_summary(gap_summary)
    options = {
        "include": include_value,
        "exclude": exclude,
        "schema": str(schema) if schema else None,
        "openapi": str(openapi) if openapi else None,
        "routes": list(routes) if routes else None,
        "ast_mode": ast_mode,
        "hybrid_mode": hybrid_mode,
        "timeout": timeout,
        "memory_limit_mb": memory_limit_mb,
    }

    return CoverageManifest(
        version=MANIFEST_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        target=str(path),
        options=options,
        models=manifest_models,
        gap_summary=manifest_gap_summary,
    )


def compare_manifests(expected: CoverageManifest, current: CoverageManifest) -> tuple[bool, str]:
    expected_payload = json.dumps(
        expected.canonical_payload(),
        sort_keys=True,
        indent=2,
    )
    current_payload = json.dumps(
        current.canonical_payload(),
        sort_keys=True,
        indent=2,
    )
    if expected_payload == current_payload:
        return True, ""

    expected_lines = expected_payload.splitlines()
    current_lines = current_payload.splitlines()
    diff = _render_diff(expected_lines, current_lines)
    return False, diff


def _render_diff(expected_lines: list[str], current_lines: list[str]) -> str:
    import difflib

    diff_lines = difflib.unified_diff(
        expected_lines,
        current_lines,
        fromfile="lockfile",
        tofile="current",
        lineterm="",
    )
    return "\n".join(diff_lines)


def _serialize_models(reports: Sequence[ModelReport]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for report in reports:
        covered, total = report.coverage
        fields = [
            {
                "name": field.name,
                "type": field.type_name,
                "provider": field.provider,
                "covered": field.covered,
                "gaps": [
                    {
                        "severity": gap.severity,
                        "reason": gap.reason,
                        "remediation": gap.remediation,
                    }
                    for gap in field.gaps
                ],
            }
            for field in sorted(report.fields, key=lambda item: item.name)
        ]
        entries.append(
            {
                "module": canonical_module_name(report.model),
                "name": report.model.__qualname__,
                "coverage": {"covered": covered, "total": total},
                "issues": list(report.issues),
                "fields": fields,
            }
        )
    entries.sort(key=lambda item: (item["module"], item["name"]))
    return entries


def _serialize_gap_summary(summary: Any) -> dict[str, Any]:
    return {
        "total_error_fields": summary.total_error_fields,
        "total_warning_fields": summary.total_warning_fields,
        "gaps": [
            {
                "severity": item.severity,
                "type": item.type_name,
                "reason": item.reason,
                "remediation": item.remediation,
                "occurrences": item.occurrences,
                "fields": item.fields,
            }
            for item in summary.summaries
        ],
    }


def _prepare_manifest_target(
    target: Path,
    schema: Path | None,
    openapi: Path | None,
    routes: Sequence[str] | None,
) -> tuple[Path, list[str]]:
    if schema and openapi:
        raise EmitError("Provide either --schema or --openapi (not both).")
    if schema:
        if not schema.exists():
            raise EmitError(f"Schema file '{schema}' does not exist.")
        ingestion = SchemaIngester().ingest_json_schema(schema)
        return ingestion.path, []
    if openapi:
        if not openapi.exists():
            raise EmitError(f"OpenAPI document '{openapi}' does not exist.")
        document = load_openapi_document(openapi)
        parsed_routes = [parse_route_value(route) for route in routes] if routes else None
        selection = select_openapi_schemas(document, parsed_routes)
        ingestion = SchemaIngester().ingest_openapi(
            openapi,
            document_bytes=dump_document(selection.document),
            fingerprint=selection.fingerprint(),
        )
        includes = [f"*.{name}" for name in selection.schemas]
        return ingestion.path, includes
    if not target.exists():
        raise EmitError(f"Target path '{target}' does not exist.")
    return target, []


__all__ = ["CoverageManifest", "build_coverage_manifest", "compare_manifests"]
