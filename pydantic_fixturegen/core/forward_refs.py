"""Forward reference registry utilities."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class ForwardReferenceError(RuntimeError):
    """Base error for forward reference configuration issues."""


class ForwardReferenceConfigurationError(ForwardReferenceError):
    """Raised when a forward reference entry is malformed."""


class ForwardReferenceResolutionError(ForwardReferenceError):
    """Raised when a configured forward reference fails to resolve."""


@dataclass(frozen=True)
class ForwardRefEntry:
    """User-provided mapping between a forward name and its target type path."""

    name: str
    target: str


@dataclass(slots=True)
class _ForwardRefTarget:
    alias: str
    module: str
    attr_path: tuple[str, ...]
    raw: str

    @classmethod
    def from_entry(cls, entry: ForwardRefEntry) -> _ForwardRefTarget:
        module, attr_path = _parse_target(entry.target)
        return cls(alias=entry.name, module=module, attr_path=attr_path, raw=entry.target)

    def resolve(self) -> type[Any]:
        try:
            module_obj = importlib.import_module(self.module)
        except Exception as exc:  # pragma: no cover - defensive against user modules
            raise ForwardReferenceResolutionError(
                f"Failed to import module '{self.module}' for forward reference '{self.alias}'."
            ) from exc

        attr: Any = module_obj
        for part in self.attr_path:
            attr = getattr(attr, part, None)
            if attr is None:
                raise ForwardReferenceResolutionError(
                    f"Attribute '{part}' missing while resolving forward reference '{self.alias}' "
                    f"from '{self.raw}'."
                )

        if not isinstance(attr, type):
            raise ForwardReferenceResolutionError(
                f"Forward reference '{self.alias}' resolved to non-type '{attr!r}'."
            )
        return attr


def _parse_target(value: str) -> tuple[str, tuple[str, ...]]:
    text = value.strip()
    module: str
    attr: str

    if ":" in text:
        module, _, attr = text.partition(":")
    else:
        module, sep, attr = text.rpartition(".")
        if not sep:
            raise ForwardReferenceConfigurationError(
                "Forward reference targets must include a module path (use 'pkg.mod:Type')."
            )

    module = module.strip()
    attr = attr.strip()
    if not module or not attr:
        raise ForwardReferenceConfigurationError(
            f"Forward reference target '{value}' must include both module and attribute names."
        )

    parts = tuple(part for part in attr.split(".") if part)
    if not parts:
        raise ForwardReferenceConfigurationError(
            f"Forward reference target '{value}' has an empty attribute path."
        )
    return module, parts


class _ForwardRefRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, _ForwardRefTarget] = {}
        self._cache: dict[str, type[Any]] = {}

    def configure(self, entries: Sequence[ForwardRefEntry]) -> None:
        targets: dict[str, _ForwardRefTarget] = {}
        cache: dict[str, type[Any]] = {}
        for entry in entries:
            alias = entry.name.strip()
            if not alias:
                raise ForwardReferenceConfigurationError(
                    "Forward reference names must be non-empty strings."
                )
            target = _ForwardRefTarget.from_entry(ForwardRefEntry(name=alias, target=entry.target))
            targets[alias] = target
            cache[alias] = target.resolve()
        self._targets = targets
        self._cache = cache

    def resolve(self, name: str) -> type[Any] | None:
        if not name:
            return None
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        target = self._targets.get(name)
        if target is None:
            return None
        resolved = target.resolve()
        self._cache[name] = resolved
        return resolved

    def snapshot(self) -> Mapping[str, str]:  # pragma: no cover - debugging helper
        return {alias: target.raw for alias, target in self._targets.items()}


_REGISTRY = _ForwardRefRegistry()


def configure_forward_refs(entries: Sequence[ForwardRefEntry]) -> None:
    """Install the provided forward reference entries, replacing previous values."""

    _REGISTRY.configure(entries)


def resolve_forward_ref(name: str) -> type[Any] | None:
    """Return the configured target for ``name`` if available."""

    return _REGISTRY.resolve(name)


__all__ = [
    "ForwardRefEntry",
    "ForwardReferenceError",
    "ForwardReferenceConfigurationError",
    "ForwardReferenceResolutionError",
    "configure_forward_refs",
    "resolve_forward_ref",
]
