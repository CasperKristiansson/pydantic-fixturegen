"""Strategy builder for field generation policies."""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Union, get_args, get_origin

import pluggy
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pydantic_fixturegen.core.config import ProviderDefaultsConfig
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.heuristics import (
    HeuristicMatch,
    HeuristicRegistry,
    create_default_heuristic_registry,
)
from pydantic_fixturegen.core.provider_defaults import (
    ProviderDefaultMatch,
    ProviderDefaultResolver,
)
from pydantic_fixturegen.core.providers import ProviderRef, ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary, summarize_model_fields
from pydantic_fixturegen.plugins.loader import get_plugin_manager


@dataclass(slots=True)
class Strategy:
    """Represents a concrete provider strategy for a field."""

    field_name: str
    summary: FieldSummary
    annotation: Any
    provider_ref: ProviderRef | None
    provider_name: str | None
    provider_kwargs: dict[str, Any] = field(default_factory=dict)
    p_none: float = 0.0
    enum_values: list[Any] | None = None
    enum_policy: str | None = None
    cycle_policy: str | None = None
    heuristic: HeuristicMatch | None = None
    type_default: ProviderDefaultMatch | None = None


@dataclass(slots=True)
class UnionStrategy:
    """Represents a strategy for union types."""

    field_name: str
    choices: list[Strategy]
    policy: str


StrategyResult = Strategy | UnionStrategy


def _describe_annotation(annotation: Any) -> str:
    if annotation is None:
        return "None"
    if isinstance(annotation, type):
        module = getattr(annotation, "__module__", "<unknown>")
        qualname = getattr(
            annotation,
            "__qualname__",
            getattr(annotation, "__name__", repr(annotation)),
        )
        return f"{module}.{qualname}"
    return repr(annotation)


class StrategyBuilder:
    """Builds provider strategies for Pydantic models."""

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        enum_policy: str = "first",
        union_policy: str = "first",
        default_p_none: float = 0.0,
        optional_p_none: float | None = None,
        plugin_manager: pluggy.PluginManager | None = None,
        array_config: Any | None = None,
        identifier_config: Any | None = None,
        number_config: Any | None = None,
        heuristic_registry: HeuristicRegistry | None = None,
        heuristics_enabled: bool = True,
        cycle_policy: str = "reuse",
        provider_defaults: ProviderDefaultsConfig | None = None,
    ) -> None:
        self.registry = registry
        self.enum_policy = enum_policy
        self.union_policy = union_policy
        self.default_p_none = default_p_none
        self.optional_p_none = optional_p_none if optional_p_none is not None else default_p_none
        self._plugin_manager = plugin_manager or get_plugin_manager()
        self._array_config = array_config
        self._identifier_config = identifier_config
        self._number_config = number_config
        self._heuristics_enabled = heuristics_enabled
        self._heuristics: HeuristicRegistry | None = None
        if heuristics_enabled:
            self._heuristics = heuristic_registry or create_default_heuristic_registry()
        self._cycle_policy = cycle_policy
        self._type_defaults = (
            ProviderDefaultResolver(provider_defaults, registry)
            if provider_defaults and provider_defaults.rules
            else None
        )

    def build_model_strategies(self, model: type[BaseModel]) -> Mapping[str, StrategyResult]:
        summaries = summarize_model_fields(model)
        strategies: dict[str, StrategyResult] = {}
        for name, model_field in model.model_fields.items():
            summary = summaries[name]
            strategies[name] = self.build_field_strategy(
                model,
                name,
                model_field.annotation,
                summary,
                field_info=model_field,
            )
        return strategies

    def build_field_strategy(
        self,
        model: type[BaseModel],
        field_name: str,
        annotation: Any,
        summary: FieldSummary,
        *,
        field_info: FieldInfo | None = None,
    ) -> StrategyResult:
        base_annotation, _ = schema_module._strip_optional(annotation)
        union_args = self._extract_union_args(base_annotation)
        if union_args:
            return self._build_union_strategy(
                model,
                field_name,
                union_args,
                field_info=field_info,
            )
        return self._build_single_strategy(
            model,
            field_name,
            summary,
            base_annotation,
            field_info=field_info,
        )

    # ------------------------------------------------------------------ helpers
    def _build_union_strategy(
        self,
        model: type[BaseModel],
        field_name: str,
        union_args: Sequence[Any],
        *,
        field_info: FieldInfo | None,
    ) -> UnionStrategy:
        choices: list[Strategy] = []
        for ann in union_args:
            summary = self._summarize_inline(ann)
            choices.append(
                self._build_single_strategy(
                    model,
                    field_name,
                    summary,
                    ann,
                    field_info=field_info,
                )
            )
        return UnionStrategy(field_name=field_name, choices=choices, policy=self.union_policy)

    def _build_single_strategy(
        self,
        model: type[BaseModel],
        field_name: str,
        summary: FieldSummary,
        annotation: Any,
        *,
        field_info: FieldInfo | None,
    ) -> Strategy:
        if summary.enum_values:
            return Strategy(
                field_name=field_name,
                summary=summary,
                annotation=annotation,
                provider_ref=None,
                provider_name="enum.static",
                provider_kwargs={},
                p_none=self.optional_p_none if summary.is_optional else self.default_p_none,
                enum_values=summary.enum_values,
                enum_policy=self.enum_policy,
            )

        if summary.type in {"model", "dataclass"}:
            p_none = self.optional_p_none if summary.is_optional else self.default_p_none
            return Strategy(
                field_name=field_name,
                summary=summary,
                annotation=annotation,
                provider_ref=None,
                provider_name=summary.type,
                provider_kwargs={},
                p_none=p_none,
                cycle_policy=self._cycle_policy,
            )

        provider: ProviderRef | None = None
        heuristic_match: HeuristicMatch | None = None
        type_default_match: ProviderDefaultMatch | None = None
        if self._type_defaults is not None:
            type_default_match = self._type_defaults.resolve(
                summary=summary,
                field_info=field_info,
            )
            if type_default_match is not None:
                provider = type_default_match.provider

        if provider is None and self._heuristics_enabled and self._heuristics is not None:
            provider, heuristic_match = self._apply_heuristics(
                model,
                field_name,
                summary,
                field_info,
            )

        if provider is None:
            provider = self.registry.get(summary.type, summary.format)
        if provider is None:
            provider = self.registry.get(summary.type)
        if provider is None and summary.type == "string":
            provider = self.registry.get("string")
        if provider is None:
            annotation_label = _describe_annotation(summary.annotation)
            field_annotation_label = (
                _describe_annotation(field_info.annotation) if field_info else None
            )
            model_label = f"{model.__module__}.{model.__qualname__}"
            context_bits = [
                f"model={model_label}",
                f"annotation={annotation_label}",
            ]
            if field_annotation_label and field_annotation_label != annotation_label:
                context_bits.append(f"field_annotation={field_annotation_label}")
            context = "; ".join(context_bits)
            raise ValueError(
                f"No provider registered for field '{field_name}' with type '{summary.type}'. "
                f"{context}"
            )

        p_none = self.default_p_none
        if summary.is_optional:
            p_none = self.optional_p_none

        provider_kwargs: dict[str, Any] = {}
        if type_default_match and type_default_match.provider_kwargs:
            provider_kwargs.update(dict(type_default_match.provider_kwargs))
        if heuristic_match and heuristic_match.provider_kwargs:
            provider_kwargs.update(heuristic_match.provider_kwargs)

        effective_summary = summary
        if heuristic_match and heuristic_match.provider_type != summary.type:
            effective_summary = replace(summary, type=heuristic_match.provider_type)

        strategy = Strategy(
            field_name=field_name,
            summary=effective_summary,
            annotation=annotation,
            provider_ref=provider,
            provider_name=provider.name,
            provider_kwargs=provider_kwargs,
            p_none=p_none,
            heuristic=heuristic_match,
            type_default=type_default_match,
        )
        if effective_summary.type == "numpy-array" and self._array_config is not None:
            strategy.provider_kwargs["array_config"] = self._array_config
        identifier_types = {
            "email",
            "url",
            "uuid",
            "payment-card",
            "secret-str",
            "secret-bytes",
            "ip-address",
            "ip-interface",
            "ip-network",
        }
        provider_type_id = provider.type_id
        if provider_type_id in identifier_types and self._identifier_config is not None:
            strategy.provider_kwargs["identifier_config"] = self._identifier_config
        numeric_types = {"int", "float", "decimal"}
        if provider_type_id in numeric_types and self._number_config is not None:
            strategy.provider_kwargs["number_config"] = self._number_config
        return self._apply_strategy_plugins(model, field_name, strategy)

    # ------------------------------------------------------------------ utilities
    def _extract_union_args(self, annotation: Any) -> Sequence[Any]:
        origin = get_origin(annotation)
        if origin in {list, set, tuple, dict}:
            return []
        if origin in {Union, types.UnionType}:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]  # noqa: E721
            if len(args) > 1:
                return args
        return []

    def _summarize_inline(self, annotation: Any) -> FieldSummary:
        return schema_module._summarize_annotation(annotation, FieldConstraints())

    def _apply_heuristics(
        self,
        model: type[BaseModel],
        field_name: str,
        summary: FieldSummary,
        field_info: FieldInfo | None,
    ) -> tuple[ProviderRef | None, HeuristicMatch | None]:
        if not self._heuristics_enabled or self._heuristics is None:
            return None, None
        match = self._heuristics.evaluate(
            model=model,
            field_name=field_name,
            summary=summary,
            field_info=field_info,
        )
        if match is None:
            return None, None
        provider = self.registry.get(match.provider_type, match.provider_format)
        if provider is None:
            provider = self.registry.get(match.provider_type)
        if provider is None:
            return None, None
        return provider, match

    def _apply_strategy_plugins(
        self,
        model: type[BaseModel],
        field_name: str,
        strategy: Strategy,
    ) -> Strategy:
        results = self._plugin_manager.hook.pfg_modify_strategy(
            model=model,
            field_name=field_name,
            strategy=strategy,
        )
        for result in results:
            if isinstance(result, Strategy):
                strategy = result
        return strategy


__all__ = ["Strategy", "UnionStrategy", "StrategyBuilder", "StrategyResult"]
