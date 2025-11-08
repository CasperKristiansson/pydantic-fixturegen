"""CLI command for injecting example payloads into OpenAPI specs."""

from __future__ import annotations

from importlib import util as import_util
from pathlib import Path
from types import ModuleType

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.openapi import (
    dump_document,
    load_openapi_document,
    select_openapi_schemas,
)
from pydantic_fixturegen.core.schema_ingest import SchemaIngester
from pydantic_fixturegen.core.seed import SeedManager

SPEC_ARGUMENT = typer.Argument(..., help="Path to an OpenAPI document (YAML or JSON).")

OUT_OPTION = typer.Option(..., "--out", "-o", help="Destination for the updated document.")

SEED_OPTION = typer.Option(None, "--seed", help="Seed override for deterministic examples.")


def register(app: typer.Typer) -> None:
    @app.command("examples")
    def gen_examples(
        spec: Path = SPEC_ARGUMENT,
        out: Path = OUT_OPTION,
        seed: int | None = SEED_OPTION,
    ) -> None:
        document = load_openapi_document(spec)
        selection = select_openapi_schemas(document, routes=None)
        ingester = SchemaIngester()
        ingestion = ingester.ingest_openapi(
            spec.resolve(),
            document_bytes=dump_document(document),
            fingerprint=selection.fingerprint(),
        )

        generator = InstanceGenerator(
            config=GenerationConfig(seed=SeedManager(seed=seed).normalized_seed if seed else None)
        )

        module = _load_module_from_path(ingestion.path)

        for schema_name in selection.schemas:
            model = getattr(module, schema_name, None)
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                continue
            instance = generator.generate_one(model)
            if instance is None:
                continue
            example_payload = instance.model_dump(mode="json")
            components = document.setdefault("components", {}).setdefault("schemas", {})
            schema = components.setdefault(schema_name, {})
            schema["example"] = example_payload

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dump_document(document).decode("utf-8"), encoding="utf-8")
        typer.echo(f"Examples written to {out}")


def _load_module_from_path(path: Path) -> ModuleType:
    spec = import_util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"Failed to import generated module from {path}")
    module = import_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


__all__ = ["register"]
