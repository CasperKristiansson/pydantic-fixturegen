"""Schema emitter utilities."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


@dataclass(slots=True)
class SchemaEmitConfig:
    output_path: Path
    indent: int | None = 2
    ensure_ascii: bool = False


def emit_model_schema(
    model: type[BaseModel],
    *,
    output_path: str | Path,
    indent: int | None = 2,
    ensure_ascii: bool = False,
) -> Path:
    """Write the model JSON schema to ``output_path``."""

    config = SchemaEmitConfig(
        output_path=Path(output_path),
        indent=_normalise_indent(indent),
        ensure_ascii=ensure_ascii,
    )
    schema = model.model_json_schema()
    payload = json.dumps(
        schema,
        indent=config.indent,
        ensure_ascii=config.ensure_ascii,
        sort_keys=True,
    )
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(payload, encoding="utf-8")
    return config.output_path


def emit_models_schema(
    models: Iterable[type[BaseModel]],
    *,
    output_path: str | Path,
    indent: int | None = 2,
    ensure_ascii: bool = False,
) -> Path:
    """Emit a combined schema referencing each model by its qualified name."""

    config = SchemaEmitConfig(
        output_path=Path(output_path),
        indent=_normalise_indent(indent),
        ensure_ascii=ensure_ascii,
    )
    combined: dict[str, Any] = {}
    for model in models:
        combined[model.__name__] = model.model_json_schema()

    payload = json.dumps(
        combined,
        indent=config.indent,
        ensure_ascii=config.ensure_ascii,
        sort_keys=True,
    )
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(payload, encoding="utf-8")
    return config.output_path


def _normalise_indent(indent: int | None) -> int | None:
    if indent in (None, 0):
        return None
    if indent < 0:
        raise ValueError("indent must be >= 0")
    return indent


__all__ = ["SchemaEmitConfig", "emit_model_schema", "emit_models_schema"]
