"""FastAPI-focused CLI commands."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

import typer

from pydantic_fixturegen._warnings import apply_warning_filters
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.fastapi_support import FastAPISmokeSuite, build_mock_app

from ..logging import get_logger

TARGET_ARGUMENT = typer.Argument(..., help="FastAPI app import path (module:attr).")

OUT_OPTION = typer.Option(
    Path("tests/test_fastapi_smoke.py"),
    "--out",
    "-o",
    help="Destination for the generated pytest suite.",
)

SEED_OPTION = typer.Option(None, "--seed", help="Seed override for deterministic payloads.")

DEPENDENCY_OVERRIDE_OPTION = typer.Option(
    None,
    "--dependency-override",
    help="Override dependencies as original=override (module.attr pairs).",
)

HOST_OPTION = typer.Option("127.0.0.1", "--host", help="Host for the mock server.")
PORT_OPTION = typer.Option(8000, "--port", help="Port for the mock server.")


app = typer.Typer(help="FastAPI helpers (smoke tests, mock servers).")


@app.command("smoke")
def fastapi_smoke(
    target: str = TARGET_ARGUMENT,
    out: Path = OUT_OPTION,
    seed: int | None = SEED_OPTION,
    dependency_override: list[str] | None = DEPENDENCY_OVERRIDE_OPTION,
) -> None:
    apply_warning_filters()
    suite = FastAPISmokeSuite(
        target=target,
        seed=seed,
        dependency_overrides=list(dependency_override or ()),
    )
    content = suite.build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    typer.echo(f"Smoke tests written to {out}")


@app.command("serve")
def fastapi_serve(
    target: str = TARGET_ARGUMENT,
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    seed: int | None = SEED_OPTION,
    dependency_override: list[str] | None = DEPENDENCY_OVERRIDE_OPTION,
) -> None:
    apply_warning_filters()
    overrides = _resolve_dependency_overrides(list(dependency_override or ()))
    mock_app = build_mock_app(target=target, seed=seed, dependency_overrides=overrides)
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DiscoveryError(
            "Running the mock server requires 'uvicorn'. Install the fastapi extra via "
            "`pip install pydantic-fixturegen[fastapi]`."
        ) from exc
    logger = get_logger()
    logger.info("Starting FastAPI mock server", event="fastapi_mock_start", host=host, port=port)
    uvicorn.run(mock_app, host=host, port=port)


def _resolve_dependency_overrides(
    pairs: Iterable[str],
) -> list[tuple[Callable[..., object], Callable[..., object]]]:
    resolved: list[tuple[Callable[..., object], Callable[..., object]]] = []
    for entry in pairs:
        if "=" not in entry:
            raise DiscoveryError("Dependency overrides must be formatted as original=override.")
        original_expr, override_expr = entry.split("=", 1)
        original = _import_object(original_expr.strip())
        override = _import_object(override_expr.strip())
        resolved.append((original, override))
    return resolved


def _import_object(expr: str) -> Callable[..., object]:
    if ":" in expr:
        module_name, attr = expr.split(":", 1)
    elif "." in expr:
        module_name, attr = expr.rsplit(".", 1)
    else:  # pragma: no cover - invalid input
        raise DiscoveryError("Object paths must be module.attr or module:attr.")
    module = __import__(module_name, fromlist=[attr])
    obj = getattr(module, attr, None)
    if obj is None:
        raise DiscoveryError(f"Attribute '{attr}' not found in module '{module_name}'.")
    return cast(Callable[..., object], obj)


__all__ = ["app"]
