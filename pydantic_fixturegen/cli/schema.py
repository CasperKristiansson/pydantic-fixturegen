"""Schema utilities exposed via the CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from pydantic_fixturegen.core.config_schema import get_config_schema_json

OUT_OPTION = typer.Option(None, "--out", "-o", help="File path to write the schema.")
PRETTY_OPTION = typer.Option(
    True,
    "--pretty",
    "--compact",
    help="Pretty-print output with indentation.",
)


app = typer.Typer(help="Inspect and export JSON Schemas.")


@app.callback()
def schema_root() -> None:  # noqa: D401 - CLI callback
    """Schema command group."""


@app.command("config")
def schema_config(  # noqa: D401 - CLI command
    out: Path | None = OUT_OPTION,
    pretty: bool = PRETTY_OPTION,
) -> None:
    """Emit the JSON Schema that describes project configuration."""

    indent = 2 if pretty else None
    payload = get_config_schema_json(indent=indent)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(payload.rstrip())


__all__ = ["app"]
