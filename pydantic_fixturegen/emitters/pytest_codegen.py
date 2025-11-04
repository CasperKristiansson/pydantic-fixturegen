"""Emit pytest fixture modules from Pydantic models."""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat
from typing import Any, Literal, cast

from pydantic import BaseModel

from pydantic_fixturegen.core.constraint_report import ConstraintReporter
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.io_utils import WriteResult, write_atomic_text
from pydantic_fixturegen.core.version import build_artifact_header

DEFAULT_SCOPE = "function"
ALLOWED_SCOPES: set[str] = {"function", "module", "session"}
DEFAULT_STYLE: Literal["functions", "factory", "class"] = "functions"
DEFAULT_RETURN_TYPE: Literal["model", "dict"] = "model"


@dataclass(slots=True)
class PytestEmitConfig:
    """Configuration for pytest fixture emission."""

    scope: str = DEFAULT_SCOPE
    style: Literal["functions", "factory", "class"] = DEFAULT_STYLE
    return_type: Literal["model", "dict"] = DEFAULT_RETURN_TYPE
    cases: int = 1
    seed: int | None = None
    optional_p_none: float | None = None
    model_digest: str | None = None
    hash_compare: bool = True
    per_model_seeds: Mapping[str, int] | None = None
    time_anchor: datetime.datetime | None = None


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
    if cfg.scope not in ALLOWED_SCOPES:
        raise ValueError(f"Unsupported fixture scope: {cfg.scope!r}")
    if cfg.cases < 1:
        raise ValueError("cases must be >= 1.")
    if cfg.style not in {"functions", "factory", "class"}:
        raise ValueError(f"Unsupported pytest fixture style: {cfg.style!r}")
    if cfg.return_type not in {"model", "dict"}:
        raise ValueError(f"Unsupported return_type: {cfg.return_type!r}")

    def _build_generator(seed_value: int | None) -> InstanceGenerator:
        generation_config = GenerationConfig(
            seed=seed_value,
            time_anchor=cfg.time_anchor,
        )
        if cfg.optional_p_none is not None:
            generation_config.optional_p_none = cfg.optional_p_none
        return InstanceGenerator(config=generation_config)

    shared_generator: InstanceGenerator | None = None

    model_entries: list[_ModelEntry] = []
    fixture_names: dict[str, int] = {}
    helper_names: dict[str, int] = {}

    per_model_seeds = cfg.per_model_seeds or {}
    constraint_reporters: list[ConstraintReporter] = []

    for model in models:
        model_id = f"{model.__module__}.{model.__qualname__}"
        if per_model_seeds:
            seed_value = per_model_seeds.get(model_id, cfg.seed)
            generator = _build_generator(seed_value)
        else:
            if shared_generator is None:
                shared_generator = _build_generator(cfg.seed)
            generator = shared_generator

        instances = generator.generate(model, count=cfg.cases)
        if len(instances) < cfg.cases:
            raise RuntimeError(
                f"Failed to generate {cfg.cases} instance(s) for {model.__qualname__}."
            )
        if per_model_seeds:
            constraint_reporters.append(generator.constraint_report)
        data = [_model_to_literal(instance) for instance in instances]
        base_name = model.__name__
        if cfg.style in {"factory", "class"}:
            base_name = f"{base_name}_factory"
        fixture_name = _unique_fixture_name(base_name, fixture_names)
        helper_name = None
        if cfg.style == "class":
            helper_base = f"{model.__name__}Factory"
            helper_name = _unique_helper_name(helper_base, helper_names)
        model_entries.append(
            _ModelEntry(
                model=model,
                data=data,
                fixture_name=fixture_name,
                helper_name=helper_name,
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
    aggregate_report = ConstraintReporter()
    if shared_generator is not None and not per_model_seeds:
        aggregate_report.merge_from(shared_generator.constraint_report)
    else:
        for reporter in constraint_reporters:
            aggregate_report.merge_from(reporter)

    if cfg.time_anchor is not None:
        result.metadata = result.metadata or {}
        result.metadata["time_anchor"] = cfg.time_anchor.isoformat()

    summary = aggregate_report.summary()
    if summary.get("models"):
        result.metadata = result.metadata or {}
        result.metadata["constraints"] = summary
    return result


# --------------------------------------------------------------------------- rendering helpers
@dataclass(slots=True)
class _ModelEntry:
    model: type[BaseModel]
    data: list[dict[str, Any]]
    fixture_name: str
    helper_name: str | None = None


def _render_module(*, entries: Iterable[_ModelEntry], config: PytestEmitConfig) -> str:
    entries_list = list(entries)
    models_metadata = ", ".join(
        f"{entry.model.__module__}.{entry.model.__name__}" for entry in entries_list
    )
    header_extras = {
        "style": config.style,
        "scope": config.scope,
        "return": config.return_type,
        "cases": config.cases,
        "models": models_metadata,
    }
    if config.time_anchor is not None:
        header_extras["time_anchor"] = config.time_anchor.isoformat()

    header = build_artifact_header(
        seed=config.seed,
        model_digest=config.model_digest,
        extras=header_extras,
    )

    needs_any = config.return_type == "dict" or config.style in {"factory", "class"}
    needs_callable = config.style == "factory"
    module_imports = _collect_model_imports(entries_list)

    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append(f"# {header}")
    lines.append("")
    lines.append("import pytest")
    typing_imports: list[str] = []
    if needs_any:
        typing_imports.append("Any")
    if needs_callable:
        typing_imports.append("Callable")
    if typing_imports:
        items = ", ".join(sorted(set(typing_imports)))
        lines.append(f"from typing import {items}")
    for module, names in module_imports.items():
        joined = ", ".join(sorted(names))
        lines.append(f"from {module} import {joined}")

    for entry in entries_list:
        if config.style == "class":
            lines.append("")
            lines.extend(_render_factory_class(entry, config=config))
        lines.append("")
        lines.extend(
            _render_fixture(entry, config=config),
        )

    lines.append("")
    return _format_code("\n".join(lines))


def _collect_model_imports(entries: Iterable[_ModelEntry]) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for entry in entries:
        imports.setdefault(entry.model.__module__, set()).add(entry.model.__name__)
    return imports


def _render_fixture(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    if config.style == "functions":
        return _render_functions_fixture(entry, config=config)
    if config.style == "factory":
        return _render_factory_fixture(entry, config=config)
    return _render_class_fixture(entry, config=config)


def _render_functions_fixture(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    annotation = entry.model.__name__ if config.return_type == "model" else "dict[str, Any]"
    has_params = len(entry.data) > 1
    params_literal = _format_literal(entry.data) if has_params else None

    lines: list[str] = []
    if has_params:
        lines.append(f'@pytest.fixture(scope="{config.scope}", params={params_literal})')
    else:
        lines.append(f'@pytest.fixture(scope="{config.scope}")')

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
        lines.append("    return dict(data)")

    return lines


def _render_factory_fixture(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    return_annotation = entry.model.__name__ if config.return_type == "model" else "dict[str, Any]"
    fixture_annotation = f"Callable[[dict[str, Any] | None], {return_annotation}]"
    has_params = len(entry.data) > 1
    params_literal = _format_literal(entry.data) if has_params else None

    lines: list[str] = []
    if has_params:
        lines.append(f'@pytest.fixture(scope="{config.scope}", params={params_literal})')
    else:
        lines.append(f'@pytest.fixture(scope="{config.scope}")')

    arglist = "request" if has_params else ""
    signature = f"def {entry.fixture_name}({arglist}) -> {fixture_annotation}:"
    lines.append(signature)

    if has_params:
        lines.append("    base_data = request.param")
    else:
        base_literal = _format_literal(entry.data[0])
        lines.extend(_format_assignment_lines("base_data", base_literal))

    lines.append(
        "    def builder(overrides: dict[str, Any] | None = None) -> " + return_annotation + ":"
    )
    lines.append("        data = dict(base_data)")
    lines.append("        if overrides:")
    lines.append("            data.update(overrides)")
    if config.return_type == "model":
        lines.append(f"        return {entry.model.__name__}.model_validate(data)")
    else:
        lines.append("        return dict(data)")
    lines.append("    return builder")

    return lines


def _render_factory_class(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    class_name = entry.helper_name or f"{entry.model.__name__}Factory"
    return_annotation = entry.model.__name__ if config.return_type == "model" else "dict[str, Any]"

    lines = [f"class {class_name}:"]
    lines.append("    def __init__(self, base_data: dict[str, Any]) -> None:")
    lines.append("        self._base_data = dict(base_data)")
    lines.append("")
    lines.append(f"    def build(self, **overrides: Any) -> {return_annotation}:")
    lines.append("        data = dict(self._base_data)")
    lines.append("        if overrides:")
    lines.append("            data.update(overrides)")
    if config.return_type == "model":
        lines.append(f"        return {entry.model.__name__}.model_validate(data)")
    else:
        lines.append("        return dict(data)")

    return lines


def _render_class_fixture(entry: _ModelEntry, *, config: PytestEmitConfig) -> list[str]:
    class_name = entry.helper_name or f"{entry.model.__name__}Factory"
    annotation = class_name
    has_params = len(entry.data) > 1
    params_literal = _format_literal(entry.data) if has_params else None

    lines: list[str] = []
    if has_params:
        lines.append(f'@pytest.fixture(scope="{config.scope}", params={params_literal})')
    else:
        lines.append(f'@pytest.fixture(scope="{config.scope}")')

    arglist = "request" if has_params else ""
    signature = f"def {entry.fixture_name}({arglist}) -> {annotation}:"
    lines.append(signature)

    if has_params:
        lines.append("    base_data = request.param")
    else:
        base_literal = _format_literal(entry.data[0])
        lines.extend(_format_assignment_lines("base_data", base_literal))

    lines.append(f"    return {class_name}(base_data)")

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


def _unique_helper_name(base: str, seen: dict[str, int]) -> str:
    count = seen.get(base, 0)
    seen[base] = count + 1
    if count == 0:
        return base
    return f"{base}{count + 1}"


_CAMEL_CASE_PATTERN_1 = re.compile("(.)([A-Z][a-z]+)")
_CAMEL_CASE_PATTERN_2 = re.compile("([a-z0-9])([A-Z])")


def _to_snake_case(name: str) -> str:
    name = _CAMEL_CASE_PATTERN_1.sub(r"\1_\2", name)
    name = _CAMEL_CASE_PATTERN_2.sub(r"\1_\2", name)
    return name.lower()


def _model_to_literal(instance: BaseModel) -> dict[str, Any]:
    raw = instance.model_dump(mode="json")
    serialized = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return cast(dict[str, Any], json.loads(serialized))


def _format_code(source: str) -> str:
    formatter = shutil.which("ruff")
    if not formatter:
        return source

    try:
        proc = subprocess.run(
            [formatter, "format", "--stdin-filename", "fixtures.py", "-"],
            input=source.encode("utf-8"),
            capture_output=True,
            check=False,
        )
    except OSError:
        return source

    if proc.returncode != 0 or not proc.stdout:
        return source

    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return source
