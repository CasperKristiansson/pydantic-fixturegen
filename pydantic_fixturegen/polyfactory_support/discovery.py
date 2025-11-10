"""Discovery helpers for Polyfactory integrations."""

from __future__ import annotations

import importlib
import sys
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from ..logging import Logger

POLYFACTORY_MODEL_FACTORY: type[Any] | None
try:  # pragma: no cover - runtime import with graceful fallback
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from polyfactory.factories.pydantic_factory import ModelFactory as _RuntimeModelFactory
except Exception:  # pragma: no cover - optional dependency missing
    POLYFACTORY_MODEL_FACTORY = None
else:
    POLYFACTORY_MODEL_FACTORY = _RuntimeModelFactory


@dataclass(slots=True)
class PolyfactoryBinding:
    """Represents a discovered Polyfactory factory for a Pydantic model."""

    model: type[BaseModel]
    factory: type[object]
    source: str

    @property
    def label(self) -> str:
        return self.source


def discover_polyfactory_bindings(
    *,
    model_classes: Iterable[type[BaseModel]],
    discovery_modules: Sequence[str],
    extra_modules: Sequence[str],
    logger: Logger | None = None,
) -> list[PolyfactoryBinding]:
    """Collect Polyfactory factories that can delegate model generation."""

    if POLYFACTORY_MODEL_FACTORY is None:
        return []

    module_queue: list[tuple[int, ModuleType]] = []
    temp_modules: list[str] = []
    seen_modules: set[str] = set()

    def enqueue(module_name: str, priority: int) -> None:
        if not module_name or module_name in seen_modules:
            return
        was_loaded = module_name not in sys.modules
        module = _load_module(module_name)
        if module is None:
            if priority == 0 and logger is not None:
                logger.warn(
                    "Failed to import Polyfactory module",
                    event="polyfactory_module_import_failed",
                    module=module_name,
                )
            return
        seen_modules.add(module_name)
        module_queue.append((priority, module))
        if was_loaded:
            temp_modules.append(module_name)

    model_module_names = {cls.__module__ for cls in model_classes if hasattr(cls, "__module__")}
    for module_name in extra_modules:
        enqueue(module_name, 0)

    for module_name in discovery_modules:
        enqueue(module_name, 1)

    for module_name in model_module_names:
        enqueue(module_name, 1)
        for candidate in _derive_candidate_modules(module_name):
            enqueue(candidate, 2)

    bindings: dict[type[BaseModel], PolyfactoryBinding] = {}
    for _, module in sorted(module_queue, key=lambda item: item[0]):
        for binding in _bindings_from_module(module):
            if binding.model in bindings:
                continue
            bindings[binding.model] = binding
            if logger is not None:
                logger.info(
                    "Polyfactory delegate registered",
                    event="polyfactory_delegate_registered",
                    model=binding.model.__qualname__,
                    factory=binding.label,
                )

    if temp_modules:
        for module_name in temp_modules:
            sys.modules.pop(module_name, None)
    return list(bindings.values())


def _load_module(module_name: str) -> ModuleType | None:
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    try:
        return importlib.import_module(module_name)
    except Exception:  # pragma: no cover - best-effort import
        return None


def _derive_candidate_modules(module_name: str) -> set[str]:
    parts = [segment for segment in module_name.split(".") if segment]
    candidates: set[str] = set()
    for index in range(1, len(parts) + 1):
        prefix = ".".join(parts[:index])
        candidates.add(f"{prefix}.factories")
        candidates.add(f"{prefix}.factory")
    if parts:
        candidates.add(f"{parts[0]}.factories")
    candidates.discard(module_name)
    return {candidate for candidate in candidates if candidate}


def _bindings_from_module(module: ModuleType) -> list[PolyfactoryBinding]:
    if POLYFACTORY_MODEL_FACTORY is None:
        return []

    bindings: list[PolyfactoryBinding] = []
    namespace = getattr(module, "__dict__", {})
    for value in namespace.values():
        if not isinstance(value, type):
            continue
        if value is POLYFACTORY_MODEL_FACTORY:
            continue
        try:
            if not issubclass(value, POLYFACTORY_MODEL_FACTORY):
                continue
        except TypeError:  # pragma: no cover - defensive
            continue
        model = getattr(value, "__model__", None)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        source = f"{module.__name__}.{value.__name__}"
        bindings.append(PolyfactoryBinding(model=model, factory=value, source=source))
    return bindings


__all__ = ["PolyfactoryBinding", "discover_polyfactory_bindings"]
