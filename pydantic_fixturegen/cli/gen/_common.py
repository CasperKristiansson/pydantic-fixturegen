"""Shared helpers for generation CLI commands."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from pydantic import BaseModel

from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult, discover

__all__ = [
    "clear_module_cache",
    "discover_models",
    "load_model_class",
    "split_patterns",
]


_module_cache: dict[str, ModuleType] = {}


def clear_module_cache() -> None:
    """Clear cached module imports used during CLI execution."""

    _module_cache.clear()


def split_patterns(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def discover_models(
    path: Path,
    *,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> IntrospectionResult:
    return discover(
        [path],
        method="import",
        include=list(include or ()),
        exclude=list(exclude or ()),
        public_only=False,
    )


def load_model_class(model_info: IntrospectedModel) -> type[BaseModel]:
    module = _load_module(model_info.module, Path(model_info.locator))
    attr = getattr(module, model_info.name, None)
    if not isinstance(attr, type) or not issubclass(attr, BaseModel):
        raise RuntimeError(
            f"Attribute {model_info.name!r} in module {module.__name__} is not a Pydantic BaseModel."
        )
    return attr


def _load_module(module_name: str, locator: Path) -> ModuleType:
    module = _module_cache.get(module_name)
    if module is not None:
        return module

    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = getattr(existing, "__file__", None)
        if existing_path and Path(existing_path).resolve() == locator.resolve():
            _module_cache[module_name] = existing
            return existing

    return _import_module_by_path(module_name, locator)


def _import_module_by_path(module_name: str, path: Path) -> ModuleType:
    if not path.exists():
        raise RuntimeError(f"Could not locate module source at {path}.")

    sys_path_entry = str(path.parent.resolve())
    if sys_path_entry not in sys.path:
        sys.path.insert(0, sys_path_entry)

    unique_name = module_name
    if module_name in sys.modules:
        unique_name = f"{module_name}_pfg_{len(_module_cache)}"

    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}.")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - surface to caller
        raise RuntimeError(f"Error importing module {path}: {exc}") from exc

    _module_cache[module_name] = module
    return module
