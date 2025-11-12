"""Field override definitions and resolution helpers."""

from __future__ import annotations

import copy
import fnmatch
import importlib
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import Any, cast

from faker import Faker

from .config import ConfigError
from .schema import FieldSummary

_UNSET = object()


@dataclass(slots=True, frozen=True)
class FieldOverrideContext:
    """Context object passed to override callables."""

    model: type[Any]
    field_name: str
    alias: str | None
    summary: FieldSummary | None
    faker: Faker
    random: random.Random
    values: Mapping[str, Any]
    path: str


@dataclass(slots=True, frozen=True)
class FieldOverride:
    """Normalized representation of a per-field override."""

    provider: str | None = None
    provider_format: str | None = None
    provider_kwargs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    value: Any = _UNSET
    factory: str | None = None
    factory_args: tuple[Any, ...] = ()
    factory_kwargs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    ignore: bool = False
    require: bool = False
    post_generate: str | None = None
    post_args: tuple[Any, ...] = ()
    post_kwargs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    p_none: float | None = None
    union_policy: str | None = None
    enum_policy: str | None = None

    @property
    def has_value_override(self) -> bool:
        return self.value is not _UNSET or self.factory is not None

    @property
    def affects_strategy(self) -> bool:
        return any(
            (
                self.provider,
                self.provider_format,
                self.provider_kwargs,
                self.p_none is not None,
                self.enum_policy,
                self.union_policy,
            )
        )

    def resolve_value(self, context: FieldOverrideContext) -> Any:
        if self.factory is not None:
            func = _load_callable(self.factory)
            return func(context, *self.factory_args, **self.factory_kwargs)
        if self.value is _UNSET:
            raise ConfigError(f"Override for '{context.path}' does not specify a value or factory.")
        return copy.deepcopy(self.value)

    def apply_post(self, value: Any, context: FieldOverrideContext) -> Any:
        if self.post_generate is None:
            return value
        func = _load_callable(self.post_generate)
        return func(value, context, *self.post_args, **self.post_kwargs)


@dataclass(slots=True, frozen=True)
class _Pattern:
    raw: str
    index: int
    is_regex: bool = field(init=False)
    regex: re.Pattern[str] | None = field(init=False)
    specificity: tuple[int, int, int] = field(init=False)

    def __post_init__(self) -> None:
        pattern = self.raw.strip()
        if not pattern:
            raise ConfigError("Override patterns must be non-empty strings.")
        object.__setattr__(self, "is_regex", pattern.startswith("re:"))
        if self.is_regex:
            compiled = re.compile(pattern[3:])
            object.__setattr__(self, "regex", compiled)
            object.__setattr__(self, "specificity", (1000, -len(pattern), -self.index))
        else:
            wildcard_count = pattern.count("*") + pattern.count("?")
            segments = pattern.count(".") + 1
            specificity = (wildcard_count, -segments, -len(pattern))
            object.__setattr__(self, "regex", None)
            object.__setattr__(self, "specificity", specificity)

    def matches(self, candidate: str | None) -> bool:
        if not candidate:
            return False
        if self.is_regex:
            assert self.regex is not None
            return bool(self.regex.fullmatch(candidate))
        return fnmatch.fnmatchcase(candidate, self.raw)


@dataclass(slots=True, frozen=True)
class _FieldEntry:
    matcher: _Pattern
    override: FieldOverride

    def matches(self, field_name: str, aliases: Sequence[str] | None = None) -> bool:
        if self.matcher.matches(field_name):
            return True
        if aliases:
            return any(self.matcher.matches(alias) for alias in aliases if alias)
        return False


@dataclass(slots=True, frozen=True)
class OverrideDescriptor:
    model_pattern: str
    field_pattern: str
    override: FieldOverride


@dataclass(slots=True, frozen=True)
class _ModelEntry:
    matcher: _Pattern
    fields: tuple[_FieldEntry, ...]

    def resolve(
        self,
        model_keys: Sequence[str],
        field_name: str,
        aliases: Sequence[str] | None,
    ) -> tuple[tuple[int, int, int], int, FieldOverride] | None:
        if not any(self.matcher.matches(key) for key in model_keys if key):
            return None
        best: tuple[int, int, int] | None = None
        best_index = 0
        selected: FieldOverride | None = None
        for entry in self.fields:
            if not entry.matches(field_name, aliases):
                continue
            spec = entry.matcher.specificity
            if best is None or spec < best:
                best = spec
                best_index = entry.matcher.index
                selected = entry.override
        if best is None or selected is None:
            return None
        return best, best_index, selected


class FieldOverrideSet:
    """Collection of model/field override definitions with precedence rules."""

    def __init__(self, entries: Sequence[_ModelEntry]) -> None:
        self._entries = tuple(entries)

    def resolve(
        self,
        *,
        model_keys: Sequence[str],
        field_name: str,
        aliases: Sequence[str] | None = None,
    ) -> FieldOverride | None:
        best: tuple[tuple[int, int, int], int, tuple[int, int, int], int] | None = None
        selected: FieldOverride | None = None
        for entry in self._entries:
            resolution = entry.resolve(model_keys, field_name, aliases)
            if resolution is None:
                continue
            field_spec, field_index, override = resolution
            key = (entry.matcher.specificity, entry.matcher.index, field_spec, field_index)
            if best is None or key < best:
                best = key
                selected = override
        return selected

    def describe(self) -> tuple[OverrideDescriptor, ...]:
        descriptors: list[OverrideDescriptor] = []
        for entry in self._entries:
            model_pattern = entry.matcher.raw
            for field_entry in entry.fields:
                descriptors.append(
                    OverrideDescriptor(
                        model_pattern=model_pattern,
                        field_pattern=field_entry.matcher.raw,
                        override=field_entry.override,
                    )
                )
        return tuple(descriptors)


def build_field_override_set(mapping: Mapping[str, Mapping[str, Any]]) -> FieldOverrideSet | None:
    if not mapping:
        return None
    model_entries: list[_ModelEntry] = []
    for model_index, (model_pattern, field_map) in enumerate(mapping.items()):
        if not isinstance(field_map, Mapping):
            raise ConfigError("Override model entries must map to field definitions.")
        field_entries: list[_FieldEntry] = []
        for field_index, (field_pattern, raw_config) in enumerate(field_map.items()):
            override = _build_field_override(
                model_pattern,
                field_pattern,
                raw_config,
            )
            matcher = _Pattern(field_pattern, field_index)
            field_entries.append(_FieldEntry(matcher=matcher, override=override))
        if field_entries:
            model_entries.append(
                _ModelEntry(
                    matcher=_Pattern(model_pattern, model_index),
                    fields=tuple(field_entries),
                )
            )
    if not model_entries:
        return None
    return FieldOverrideSet(model_entries)


def _build_field_override(
    model_pattern: str,
    field_pattern: str,
    config: Any,
) -> FieldOverride:
    if not isinstance(config, Mapping):
        raise ConfigError(
            f"Override '{model_pattern}.{field_pattern}' must be a mapping of options."
        )

    provider = _coerce_optional_str(config.get("provider"), label="provider")
    provider_format = _coerce_optional_str(
        config.get("provider_format", config.get("format")),
        label="provider_format",
    )
    provider_kwargs = _ensure_mapping(
        config.get("provider_kwargs"),
        f"{model_pattern}.{field_pattern}.provider_kwargs",
    )

    value = config["value"] if "value" in config else config.get("use", _UNSET)
    factory = _coerce_optional_str(
        config.get("factory") or config.get("callable"),
        label="factory",
    )
    factory_args = _coerce_tuple(
        config.get("factory_args"),
        f"{model_pattern}.{field_pattern}.factory_args",
    )
    factory_kwargs = _ensure_mapping(
        config.get("factory_kwargs"),
        f"{model_pattern}.{field_pattern}.factory_kwargs",
    )

    ignore = _coerce_bool(config.get("ignore", False))
    require = _coerce_bool(config.get("require", False))

    post_generate = _coerce_optional_str(
        config.get("post_generate") or config.get("post"),
        label="post_generate",
    )
    post_args = _coerce_tuple(
        config.get("post_args"),
        f"{model_pattern}.{field_pattern}.post_args",
    )
    post_kwargs = _ensure_mapping(
        config.get("post_kwargs"),
        f"{model_pattern}.{field_pattern}.post_kwargs",
    )

    p_none = _coerce_optional_float(config.get("p_none"))
    enum_policy = _coerce_policy(
        config.get("enum_policy"),
        {"first", "random"},
        f"{model_pattern}.{field_pattern}.enum_policy",
    )
    union_policy = _coerce_policy(
        config.get("union_policy"),
        {"first", "random"},
        f"{model_pattern}.{field_pattern}.union_policy",
    )

    if ignore and (require or value is not _UNSET or factory or post_generate):
        raise ConfigError(
            f"Override '{model_pattern}.{field_pattern}' cannot combine ignore with other options."
        )
    if require and value is _UNSET and not factory:
        # allowed but we'll enforce at runtime; still useful to warn? leave as-is
        pass
    if value is not _UNSET and factory:
        raise ConfigError(
            f"Override '{model_pattern}.{field_pattern}' cannot set both value and factory."
        )

    return FieldOverride(
        provider=provider,
        provider_format=provider_format,
        provider_kwargs=provider_kwargs,
        value=value,
        factory=factory,
        factory_args=factory_args,
        factory_kwargs=factory_kwargs,
        ignore=ignore,
        require=require,
        post_generate=post_generate,
        post_args=post_args,
        post_kwargs=post_kwargs,
        p_none=p_none,
        union_policy=union_policy,
        enum_policy=enum_policy,
    )


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} must be a mapping of key/value pairs.")
    frozen: dict[str, Any] = {}
    for key, entry in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{label} keys must be strings.")
        frozen[key] = entry
    return MappingProxyType(frozen)


def _coerce_tuple(value: Any, label: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise ConfigError(f"{label} must be provided as a list or tuple.")


def _coerce_optional_str(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{label} values must be strings when provided.")
    stripped = value.strip()
    return stripped or None


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("Override p_none must be a numeric value.") from exc
    if not (0.0 <= result <= 1.0):
        raise ConfigError("Override p_none must be between 0.0 and 1.0.")
    return result


def _coerce_policy(value: Any, allowed: set[str], label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be one of {sorted(allowed)}.")
    if value not in allowed:
        raise ConfigError(f"{label} must be one of {sorted(allowed)}.")
    return value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return False
    raise ConfigError("Override flags must be boolean values.")


@lru_cache(maxsize=256)
def _load_callable(path: str) -> Callable[..., Any]:
    if not path:
        raise ConfigError("Override callable paths must be non-empty.")
    module_name: str
    attr_path: str
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise ConfigError(f"Override callable '{path}' could not be resolved.")
        target = getattr(target, part)
    if not callable(target):
        raise ConfigError(f"Override callable '{path}' is not callable.")
    return cast(Callable[..., Any], target)


__all__ = [
    "FieldOverride",
    "FieldOverrideContext",
    "FieldOverrideSet",
    "OverrideDescriptor",
    "build_field_override_set",
]
