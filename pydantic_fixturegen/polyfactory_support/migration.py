"""Utilities for analyzing Polyfactory factories and translating overrides."""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic_fixturegen.core.seed_freeze import canonical_module_name
from pydantic_fixturegen.core.strategies import StrategyResult, UnionStrategy
from pydantic_fixturegen.polyfactory_support.discovery import PolyfactoryBinding

MIGRATION_FACTORY_WRAPPER = "pydantic_fixturegen.polyfactory_support.migration_helpers:invoke_use"
MIGRATION_POST_WRAPPER = (
    "pydantic_fixturegen.polyfactory_support.migration_helpers:invoke_post_generate"
)


@dataclass(slots=True)
class FieldReport:
    name: str
    kind: str
    detail: str
    fixturegen_provider: str | None
    translation: dict[str, Any] | None
    message: str | None = None

    @property
    def translated(self) -> bool:
        return self.translation is not None and not self.message


@dataclass(slots=True)
class FactoryReport:
    model: type[Any]
    factory: type[Any]
    source: str
    fields: list[FieldReport]

    @property
    def model_label(self) -> str:
        module = canonical_module_name(self.model)
        qualname = getattr(self.model, "__qualname__", getattr(self.model, "__name__", ""))
        return f"{module}.{qualname}" if qualname else module

    @property
    def factory_label(self) -> str:
        qualname = getattr(self.factory, "__qualname__", getattr(self.factory, "__name__", ""))
        return f"{self.factory.__module__}.{qualname}" if qualname else self.factory.__module__

    def translated_overrides(self) -> dict[str, dict[str, Any]]:
        overrides: dict[str, dict[str, Any]] = {}
        for field in self.fields:
            if not field.translated:
                continue
            overrides[field.name] = field.translation or {}
        return overrides


class _PolyfactoryIntrospectable(Protocol):
    @classmethod
    def get_model_fields(cls) -> Sequence[Any]:
        ...


def describe_strategy(strategy: StrategyResult | None) -> str | None:
    if strategy is None:
        return None
    if isinstance(strategy, UnionStrategy):
        return f"union({strategy.policy})"
    provider: str | None = None
    if strategy.provider_ref is not None:
        provider = strategy.provider_ref.name or strategy.provider_ref.type_id
        if strategy.provider_ref.format:
            provider = f"{provider}:{strategy.provider_ref.format}"
    if strategy.provider_name:
        provider = strategy.provider_name
    if strategy.heuristic is not None:
        hint = strategy.heuristic.rule
        provider = f"{provider or strategy.heuristic.provider_type} [heuristic:{hint}]"
    if strategy.type_default is not None:
        rule_name = strategy.type_default.rule.name
        provider = f"{provider or strategy.type_default.provider.type_id} [default:{rule_name}]"
    return provider


def analyze_binding(
    binding: PolyfactoryBinding,
    *,
    strategies: Mapping[str, StrategyResult] | None = None,
) -> FactoryReport:
    fields: list[FieldReport] = []
    factory_dict = getattr(binding.factory, "__dict__", {})
    factory_cls = cast(_PolyfactoryIntrospectable, binding.factory)
    model_fields = {field_meta.name for field_meta in factory_cls.get_model_fields()}
    for field_name in sorted(model_fields):
        declared = factory_dict.get(field_name)
        if declared is None:
            continue
        provider_label = describe_strategy((strategies or {}).get(field_name))
        report = _translate_field(field_name, declared, provider_label)
        fields.append(report)
    return FactoryReport(
        model=binding.model,
        factory=binding.factory,
        source=binding.source,
        fields=fields,
    )


def _translate_field(name: str, value: Any, provider_label: str | None) -> FieldReport:
    kind = type(value).__name__
    detail = repr(value)
    message: str | None = None
    translation: dict[str, Any] | None = None
    if _is_use(value):
        path, path_label = _callable_path(value.fn["value"])
        detail = f"Use({path_label})"
        if path is None:
            message = "callable could not be resolved"
        else:
            try:
                args = _serialize_list(value.args)
                kwargs = _serialize_mapping(value.kwargs)
            except ValueError as exc:
                message = str(exc)
            else:
                translation = {
                    "factory": MIGRATION_FACTORY_WRAPPER,
                    "factory_args": [path, args, kwargs],
                }
    elif _is_ignore(value):
        kind = "Ignore"
        detail = "Ignore()"
        translation = {"ignore": True}
    elif _is_require(value):
        kind = "Require"
        detail = "Require()"
        translation = {"require": True}
    elif _is_post_generated(value):
        path, path_label = _callable_path(value.fn["value"])
        detail = f"PostGenerated({path_label})"
        if path is None:
            message = "callable could not be resolved"
        else:
            try:
                args = _serialize_list(value.args)
                kwargs = _serialize_mapping(value.kwargs)
            except ValueError as exc:
                message = str(exc)
            else:
                translation = {
                    "post_generate": MIGRATION_POST_WRAPPER,
                    "post_args": [path, args, kwargs],
                }
    else:
        try:
            serialized = _serialize_value(value)
        except ValueError:
            message = "value cannot be serialized into fixturegen overrides"
        else:
            translation = {"value": serialized}
            kind = "Value"
            detail = repr(serialized)
    return FieldReport(
        name=name,
        kind=kind,
        detail=detail,
        fixturegen_provider=provider_label,
        translation=translation,
        message=message,
    )


def _callable_path(func: Any) -> tuple[str | None, str]:
    module = getattr(func, "__module__", None)
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", repr(func)))
    if module and qualname and "<locals>" not in qualname:
        return f"{module}:{qualname}", qualname
    return None, qualname


def _serialize_value(value: Any) -> Any:
    if value is None:
        raise ValueError("None values are not supported in generated overrides")
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        raw = value.value
        if isinstance(raw, (str, int, float, bool)):
            return raw
        return str(raw)
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        serialized: dict[str, Any] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise ValueError("Override keys must be strings")
            serialized[key] = _serialize_value(val)
        return serialized
    return str(value)


def _serialize_list(args: Sequence[Any]) -> list[Any]:
    return [_serialize_value(arg) for arg in args]


def _serialize_mapping(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _serialize_value(val) for key, val in kwargs.items()}


def _type_name(value: Any) -> str:
    return type(value).__name__


def _is_use(value: Any) -> bool:
    return _type_name(value) == "Use" and hasattr(value, "fn")


def _is_ignore(value: Any) -> bool:
    return _type_name(value) == "Ignore"


def _is_require(value: Any) -> bool:
    return _type_name(value) == "Require"


def _is_post_generated(value: Any) -> bool:
    return _type_name(value) == "PostGenerated" and hasattr(value, "fn")


def merge_override_maps(reports: Sequence[FactoryReport]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for report in reports:
        overrides = report.translated_overrides()
        if not overrides:
            continue
        merged.setdefault(report.model_label, {}).update(overrides)
    return merged


def render_overrides_toml(overrides: Mapping[str, Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for model in sorted(overrides):
        fields = overrides[model]
        for field in sorted(fields):
            lines.append(f'[tool.pydantic_fixturegen.overrides."{model}".{field}]')
            for key, value in fields[field].items():
                lines.append(f"{key} = {_toml_value(value)}")
            lines.append("")
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_toml_value(item) for item in value)
        return f"[{items}]"
    if isinstance(value, dict):
        items = ", ".join(f"{key} = {_toml_value(value[key])}" for key in sorted(value))
        return f"{{ {items} }}"
    return f'"{value}"'


def reports_to_jsonable(reports: Sequence[FactoryReport]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for report in reports:
        payload.append(
            {
                "model": report.model_label,
                "factory": report.factory_label,
                "source": report.source,
                "fields": [dataclasses.asdict(field) for field in report.fields],
            }
        )
    return payload


__all__ = [
    "FieldReport",
    "FactoryReport",
    "MIGRATION_FACTORY_WRAPPER",
    "MIGRATION_POST_WRAPPER",
    "analyze_binding",
    "merge_override_maps",
    "render_overrides_toml",
    "reports_to_jsonable",
]
