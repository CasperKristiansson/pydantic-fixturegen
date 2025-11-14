"""CLI command for writing coverage manifests."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from pydantic_fixturegen.cli.doctor import AST_OPTION as DOCTOR_AST_OPTION
from pydantic_fixturegen.cli.doctor import EXCLUDE_OPTION as DOCTOR_EXCLUDE_OPTION
from pydantic_fixturegen.cli.doctor import HYBRID_OPTION as DOCTOR_HYBRID_OPTION
from pydantic_fixturegen.cli.doctor import INCLUDE_OPTION as DOCTOR_INCLUDE_OPTION
from pydantic_fixturegen.cli.doctor import MEMORY_LIMIT_OPTION as DOCTOR_MEMORY_OPTION
from pydantic_fixturegen.cli.doctor import OPENAPI_OPTION as DOCTOR_OPENAPI_OPTION
from pydantic_fixturegen.cli.doctor import PATH_ARGUMENT as DOCTOR_PATH_ARGUMENT
from pydantic_fixturegen.cli.doctor import ROUTES_OPTION as DOCTOR_ROUTES_OPTION
from pydantic_fixturegen.cli.doctor import SCHEMA_OPTION as DOCTOR_SCHEMA_OPTION
from pydantic_fixturegen.cli.doctor import TIMEOUT_OPTION as DOCTOR_TIMEOUT_OPTION
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
    help="Path to the coverage manifest file.",
)

FORCE_OPTION = typer.Option(
    False,
    "--force/--no-force",
    help="Force writing the lockfile even if it already matches the current state.",
)

app = typer.Typer(
    help="Generate or refresh the coverage lockfile used by `pfg verify`.",
)


@app.command()
def lock(  # noqa: PLR0913
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
    force: bool = FORCE_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    try:
        target_path = Path(path).resolve() if path else None
        if target_path is None and schema is None and openapi is None:
            raise EmitError("Provide a module path, --schema, or --openapi.")
        manifest = build_coverage_manifest(
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
        _write_lockfile(lockfile, manifest, force=force)
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)


def _write_lockfile(lockfile: Path, manifest: CoverageManifest, *, force: bool) -> None:
    lockfile = lockfile.resolve()
    payload = manifest.to_payload()
    serialized = json.dumps(payload, indent=2)
    if lockfile.exists() and not force:
        existing = CoverageManifest.from_payload(json.loads(lockfile.read_text(encoding="utf-8")))
        matches, _ = compare_manifests(existing, manifest)
        if matches:
            typer.echo(f"Coverage lockfile already up to date ({lockfile}).")
            return
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    lockfile.write_text(serialized, encoding="utf-8")
    typer.echo(f"Wrote coverage lockfile to {lockfile}")


__all__ = ["app"]
