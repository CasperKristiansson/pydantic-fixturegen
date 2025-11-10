"""CLI command for injecting example payloads into OpenAPI specs."""

from __future__ import annotations

from importlib import util as import_util
from pathlib import Path
from types import ModuleType
from typing import Any

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
from pydantic_fixturegen.logging import Logger, get_logger

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
        logger = get_logger()
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
            if model is None:
                _log_example_skip(
                    logger,
                    schema_name,
                    reason="missing_model",
                    module_path=str(ingestion.path),
                )
                continue
            if not _is_model_like(model):
                _log_example_skip(
                    logger,
                    schema_name,
                    reason="not_model_like",
                    resolved=_describe_candidate(model),
                )
                continue
            instance = generator.generate_one(model)
            if instance is None:
                failure_payload = _collect_failure_payload(generator)
                _log_example_skip(
                    logger,
                    schema_name,
                    reason="generation_failed",
                    model=_describe_candidate(model),
                    failure=failure_payload,
                )
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


def _is_model_like(candidate: object) -> bool:
    if not isinstance(candidate, type):
        return False
    try:
        if issubclass(candidate, BaseModel):
            return True
    except TypeError:
        pass
    return hasattr(candidate, "model_fields") or hasattr(candidate, "__fields__")


def _describe_candidate(candidate: object) -> str | None:
    if candidate is None:
        return None
    if isinstance(candidate, type):
        module = getattr(candidate, "__module__", "<unknown>")
        qualname = getattr(
            candidate,
            "__qualname__",
            getattr(candidate, "__name__", repr(candidate)),
        )
        return f"{module}.{qualname}"
    return repr(candidate)


def _log_example_skip(
    logger: Logger,
    schema_name: str,
    *,
    reason: str,
    **context: Any,
) -> None:
    payload = {"schema": schema_name, "reason": reason}
    for key, value in context.items():
        if value is not None:
            payload[key] = value
    logger.warn(
        "Skipping schema during example injection",
        event="examples_skip",
        **payload,
    )


def _collect_failure_payload(generator: InstanceGenerator) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    validator = getattr(generator, "validator_failure_details", None)
    if validator:
        payload["validator_failure"] = validator
    generation = getattr(generator, "generation_failure_details", None)
    if generation:
        payload["generation_failure"] = generation
    reporter = getattr(generator, "constraint_report", None)
    if reporter is not None:
        summary = reporter.summary()
        if summary:
            payload["constraint_summary"] = summary
    return payload or None


__all__ = ["register"]
