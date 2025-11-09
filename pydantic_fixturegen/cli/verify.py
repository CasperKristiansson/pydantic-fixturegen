"""CLI command for verifying coverage manifests."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from pydantic_fixturegen.cli.doctor import (
    AST_OPTION as DOCTOR_AST_OPTION,
    EXCLUDE_OPTION as DOCTOR_EXCLUDE_OPTION,
    HYBRID_OPTION as DOCTOR_HYBRID_OPTION,
    INCLUDE_OPTION as DOCTOR_INCLUDE_OPTION,
    MEMORY_LIMIT_OPTION as DOCTOR_MEMORY_OPTION,
    OPENAPI_OPTION as DOCTOR_OPENAPI_OPTION,
    PATH_ARGUMENT as DOCTOR_PATH_ARGUMENT,
    ROUTES_OPTION as DOCTOR_ROUTES_OPTION,
    SCHEMA_OPTION as DOCTOR_SCHEMA_OPTION,
    TIMEOUT_OPTION as DOCTOR_TIMEOUT_OPTION,
)
from pydantic_fixturegen.cli.gen._common import JSON_ERRORS_OPTION, render_cli_error
from pydantic_fixturegen.core.errors import EmitError, PFGError
from pydantic_fixturegen.coverage.manifest import (
    CoverageManifest,
    build_coverage_manifest,
    compare_manifests,
)

LOCKFILE_OPTION = typer.Option(
    ".pfg-lock.json",
    "--lockfile",
    "-f",
    help="Path to the coverage manifest file to verify.",
)

app = typer.Typer(
    invoke_without_command=True,
    help="Verify that the current coverage matches the stored lockfile.",
)


@app.callback(invoke_without_command=True)
def verify(  # noqa: PLR0913
    ctx: typer.Context,
    path: str | None = DOCTOR_PATH_ARGUMENT,
    include: str | None = DOCTOR_INCLUDE_OPTION,
    exclude: str | None = DOCTOR_EXCLUDE_OPTION,
    schema: Path | None = DOCTOR_SCHEMA_OPTION,
    openapi: Path | None = DOCTOR_OPENAPI_OPTION,
    routes: list[str] | None = DOCTOR_ROUTES_OPTION,
    ast_mode: bool = DOCTOR_AST_OPTION,
    hybrid_mode: bool = DOCTOR_HYBRID_OPTION,
    timeout: float = DOCTOR_TIMEOUT_OPTION,
    memory_limit_mb: int = DOCTOR_MEMORY_OPTION,
    lockfile: Path = LOCKFILE_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx  # unused
    try:
        expected = _load_manifest(lockfile)
        target_path = Path(path).resolve() if path else None
        if target_path is None and schema is None and openapi is None:
            raise EmitError("Provide a module path, --schema, or --openapi.")
        current = build_coverage_manifest(
            target=target_path if target_path else Path("."),
            include=include,
            exclude=exclude,
            schema=schema,
            openapi=openapi,
            routes=routes,
            ast_mode=ast_mode,
            hybrid_mode=hybrid_mode,
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
        )
        matches, diff = compare_manifests(expected, current)
        if not matches:
            details = {"lockfile": str(lockfile)}
            if diff:
                details["diff"] = diff
            raise EmitError("Coverage manifest mismatch.", details=details)
        typer.echo("Coverage manifest verification succeeded.")
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)


def _load_manifest(lockfile: Path) -> CoverageManifest:
    lockfile = lockfile.resolve()
    if not lockfile.exists():
        raise EmitError(f"Lockfile '{lockfile}' does not exist.")
    payload = json.loads(lockfile.read_text(encoding="utf-8"))
    return CoverageManifest.from_payload(payload)


__all__ = ["app"]
