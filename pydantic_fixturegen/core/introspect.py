"""High-level discovery orchestration combining AST and safe import approaches."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .ast_discover import AstModel
from .ast_discover import discover_models as ast_discover
from .safe_import import safe_import_models

DiscoveryMethod = Literal["ast", "import", "hybrid"]


@dataclass(slots=True)
class IntrospectedModel:
    module: str
    name: str
    qualname: str
    locator: str
    lineno: int | None
    discovery: DiscoveryMethod
    is_public: bool


@dataclass(slots=True)
class IntrospectionResult:
    models: list[IntrospectedModel]
    warnings: list[str]
    errors: list[str]


def discover(
    paths: Iterable[Path | str],
    *,
    method: DiscoveryMethod = "hybrid",
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    public_only: bool = False,
    safe_import_timeout: float = 5.0,
    safe_import_memory_limit_mb: int = 256,
) -> IntrospectionResult:
    """Discover Pydantic models using AST, safe import, or both."""
    include_patterns = tuple(include or [])
    exclude_patterns = tuple(exclude or [])
    normalized_paths = [Path(path) for path in paths]

    models: dict[str, IntrospectedModel] = {}
    warnings: list[str] = []
    errors: list[str] = []

    if method in {"ast", "hybrid"}:
        ast_result = ast_discover(
            normalized_paths,
            infer_module=True,
            public_only=public_only,
        )
        warnings.extend(ast_result.warnings)

        for ast_model in ast_result.models:
            entry = _to_introspection_model_from_ast(ast_model)
            if _should_include(entry, include_patterns, exclude_patterns):
                models.setdefault(entry.qualname, entry)

        if method == "ast":
            return IntrospectionResult(
                models=sorted(models.values(), key=lambda m: m.qualname),
                warnings=warnings,
                errors=errors,
            )

    if method in {"import", "hybrid"}:
        safe_result = safe_import_models(
            normalized_paths,
            timeout=safe_import_timeout,
            memory_limit_mb=safe_import_memory_limit_mb,
        )
        if not safe_result.success and safe_result.error:
            errors.append(safe_result.error)
        if safe_result.stderr:
            warnings.append(safe_result.stderr.strip())

        for import_model in safe_result.models:
            entry = _to_introspection_model_from_import(import_model)
            if public_only and entry.name.startswith("_"):
                continue
            if _should_include(entry, include_patterns, exclude_patterns):
                models[entry.qualname] = entry

    return IntrospectionResult(
        models=sorted(models.values(), key=lambda m: m.qualname),
        warnings=warnings,
        errors=errors,
    )


def _should_include(
    model: IntrospectedModel,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
) -> bool:
    identifier = model.qualname
    if include_patterns and not any(
        fnmatch.fnmatchcase(identifier, pattern) for pattern in include_patterns
    ):
        return False
    return not (
        exclude_patterns
        and any(fnmatch.fnmatchcase(identifier, pattern) for pattern in exclude_patterns)
    )


def _to_introspection_model_from_ast(model: AstModel) -> IntrospectedModel:
    return IntrospectedModel(
        module=model.module,
        name=model.name,
        qualname=model.qualname,
        locator=str(model.path),
        lineno=model.lineno,
        discovery="ast",
        is_public=model.is_public,
    )


def _to_introspection_model_from_import(model: dict[str, object]) -> IntrospectedModel:
    module = str(model.get("module"))
    name = str(model.get("name"))
    qualname = str(model.get("qualname") or f"{module}.{name}")
    locator = str(model.get("path") or module)
    return IntrospectedModel(
        module=module,
        name=name,
        qualname=qualname,
        locator=locator,
        lineno=None,
        discovery="import",
        is_public=not name.startswith("_"),
    )
