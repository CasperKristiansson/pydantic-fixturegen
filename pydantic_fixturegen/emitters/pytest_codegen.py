"""Emit pytest fixture modules from Pydantic models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel

from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.io_utils import WriteResult, write_atomic_text
from pydantic_fixturegen.core.version import build_artifact_header

DEFAULT_SCOPE = "function"
DEFAULT_STYLE: Literal["functions"] = "functions"
DEFAULT_RETURN_TYPE: Literal["model", "dict"] = "model"


@dataclass(slots=True)
class PytestEmitConfig:
    """Configuration for pytest fixture emission."""

    scope: str = DEFAULT_SCOPE
    style: Literal["functions"] = DEFAULT_STYLE
    return_type: Literal["model", "dict"] = DEFAULT_RETURN_TYPE
    cases: int = 1
    seed: int | None = None
    optional_p_none: float | None = None
    model_digest: str | None = None
    hash_compare: bool = True


def emit_pytest_fixtures(
    models: Sequence[type[BaseModel]],
    *,
    output_path: str | Path,
    config: PytestEmitConfig | None = None,
) -> WriteResult:
    """Generate pytest fixture code for ``models`` and write it atomically."""

    if not models:
        raise ValueError("At least one model must be provided.")

    cfg = config or PytestEmitConfig()
    if cfg.cases < 1:
        raise ValueError("cases must be >= 1.")
    if cfg.style != "functions":
        raise ValueError(f"Unsupported pytest fixture style: {cfg.style!r}")
    if cfg.return_type not in {"model", "dict"}:
        raise ValueError(f"Unsupported return_type: {cfg.return_type!r}")

    generation_config = GenerationConfig(seed=cfg.seed)
    if cfg.optional_p_none is not None:
        generation_config.optional_p_none = cfg.optional_p_none
    generator = InstanceGenerator(config=generation_config)

    model_entries: list[_ModelEntry] = []
    fixture_names: dict[str, int] = {}

    for model in models:
        instances = generator.generate(model, count=cfg.cases)
        if len(instances) < cfg.cases:
            raise RuntimeError(f"Failed to generate {cfg.cases} instance(s) for {model.__qualname__}.")
        data = [_model_to_literal(instance) for instance in instances]
        fixture_name = _unique_fixture_name(model.__name__, fixture_names)
        model_entries.append(
            _ModelEntry(
                model=model,
                data=data,
                fixture_name=fixture_name,
            )
        )

    rendered = _render_module(
        entries=model_entries,
        config=cfg,
    )
    result = write_atomic_text(
        output_path,
        rendered,
        hash_compare=cfg.hash_compare,
    )
    return result


# --------------------------------------------------------------------------- rendering helpers
@dataclass(slots=True)
class _ModelEntry:
    model: type[BaseModel]
    data: list[dict[str, Any]]
    fixture_name: str


def _render_module(*, entries: Iterable[_ModelEntry], config: PytestEmitConfig) -> str:
    entries_list = list(entries)
    models_metadata = ", ".join(
        f"{entry.model.__module__}.{entry.model.__name__}" for entry in entries_list
    )
    header = build_artifact_header(
        seed=config.seed,
        model_digest=config.model_digest,
        extras={
            "style": config.style,
            "scope": config.scope,
            "return": config.return_type,
            "cases": config.cases,
            "models": models_metadata,
        },
    )

    needs_any = config.return_type == "dict"
    module_imports = _collect_model_imports(entries_list)

    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append(f"# {header}")
    lines.append("")
    lines.append("import pytest")
    if needs_any:
        lines.append("from typing import Any")
    for module, names in module_imports.items():
        joined = ", ".join(sorted(names))
        lines.append(f"from {module} import {joined}")

    for entry in entries_list:
        lines.append("")
        lines.extend(
            _render_fixture(entry, config=config),
        )

    lines.append("")
    return "\n".join(lines)


def _collect_model_imports(entries: Iterable[_ModelEntry]) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for entry in entries:
        imports.setdefault(entry.model.__module__, set()).add(entry.model.__name__)
    return imports


def _render_fixture(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    annotation = (
        entry.model.__name__ if config.return_type == "model" else "dict[str, Any]"
    )
    has_params = config.cases > 1
    params_literal = None
    if has_params:
        params_literal = _format_literal(entry.data)

    lines: list[str] = []
    if has_params:
        lines.append(
            f"@pytest.fixture(scope=\"{config.scope}\", params={params_literal})"
        )
    else:
        lines.append(f"@pytest.fixture(scope=\"{config.scope}\")")

    arglist = "request" if has_params else ""
    signature = f"def {entry.fixture_name}({arglist}) -> {annotation}:"
    lines.append(signature)

    if has_params:
        lines.append("    data = request.param")
    else:
        data_literal = _format_literal(entry.data[0])
        lines.extend(_format_assignment_lines("data", data_literal))

    if config.return_type == "model":
        lines.append(f"    return {entry.model.__name__}.model_validate(data)")
    else:
        lines.append("    return data")

    return lines


def _format_literal(value: Any) -> str:
    return pformat(value, width=88, sort_dicts=True)


def _format_assignment_lines(var_name: str, literal: str) -> list[str]:
    if "\n" not in literal:
        return [f"    {var_name} = {literal}"]

    pieces = literal.splitlines()
    result = [f"    {var_name} = {pieces[0]}"]
    for piece in pieces[1:]:
        result.append(f"    {piece}")
    return result


def _unique_fixture_name(base: str, seen: dict[str, int]) -> str:
    candidate = _to_snake_case(base)
    count = seen.get(candidate, 0)
    seen[candidate] = count + 1
    if count == 0:
        return candidate
    return f"{candidate}_{count + 1}"


_CAMEL_CASE_PATTERN_1 = re.compile("(.)([A-Z][a-z]+)")
_CAMEL_CASE_PATTERN_2 = re.compile("([a-z0-9])([A-Z])")


def _to_snake_case(name: str) -> str:
    name = _CAMEL_CASE_PATTERN_1.sub(r"\\1_\\2", name)
    name = _CAMEL_CASE_PATTERN_2.sub(r"\\1_\\2", name)
    return name.lower()


def _model_to_literal(instance: BaseModel) -> dict[str, Any]:
    raw = instance.model_dump(mode="json")
    serialized = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return json.loads(serialized)
