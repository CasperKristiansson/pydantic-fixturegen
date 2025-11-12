"""Schema emitter utilities."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pydantic_fixturegen.core.model_utils import model_json_schema
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext


@dataclass(slots=True)
class SchemaEmitConfig:
    output_path: Path
    indent: int | None = 2
    ensure_ascii: bool = False


def emit_model_schema(
    model: type[Any],
    *,
    output_path: str | Path,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    template: OutputTemplate | None = None,
    template_context: OutputTemplateContext | None = None,
) -> Path:
    """Write the model JSON schema to ``output_path``."""

    template_obj = template or OutputTemplate(output_path)
    context = template_context or OutputTemplateContext()
    resolved_path = template_obj.render(
        context=context,
        case_index=1 if template_obj.uses_case_index() else None,
    )

    config = SchemaEmitConfig(
        output_path=resolved_path,
        indent=_normalise_indent(indent),
        ensure_ascii=ensure_ascii,
    )
    schema = model_json_schema(model)
    payload = json.dumps(
        schema,
        indent=config.indent,
        ensure_ascii=config.ensure_ascii,
        sort_keys=True,
    )
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    if payload and not payload.endswith("\n"):
        payload += "\n"
    config.output_path.write_text(payload, encoding="utf-8")
    return config.output_path


def emit_models_schema(
    models: Iterable[type[Any]],
    *,
    output_path: str | Path,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    template: OutputTemplate | None = None,
    template_context: OutputTemplateContext | None = None,
) -> Path:
    """Emit a combined schema referencing each model by its qualified name."""

    template_obj = template or OutputTemplate(output_path)
    context = template_context or OutputTemplateContext()
    resolved_path = template_obj.render(
        context=context,
        case_index=1 if template_obj.uses_case_index() else None,
    )

    config = SchemaEmitConfig(
        output_path=resolved_path,
        indent=_normalise_indent(indent),
        ensure_ascii=ensure_ascii,
    )
    combined: dict[str, Any] = {}
    for model in sorted(models, key=lambda m: m.__name__):
        combined[model.__name__] = model_json_schema(model)

    payload = json.dumps(
        combined,
        indent=config.indent,
        ensure_ascii=config.ensure_ascii,
        sort_keys=True,
    )
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    if payload and not payload.endswith("\n"):
        payload += "\n"
    config.output_path.write_text(payload, encoding="utf-8")
    return config.output_path


def _normalise_indent(indent: int | None) -> int | None:
    if indent is None or indent == 0:
        return None
    if indent < 0:
        raise ValueError("indent must be >= 0")
    return indent


__all__ = ["SchemaEmitConfig", "emit_model_schema", "emit_models_schema"]
