"""Strategy builder for field generation policies."""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.providers import ProviderRef, ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary, summarize_model_fields


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


@dataclass(slots=True)
class UnionStrategy:
    """Represents a strategy for union types."""

    field_name: str
    choices: list[Strategy]
    policy: str


StrategyResult = Strategy | UnionStrategy


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
    ) -> None:
        self.registry = registry
        self.enum_policy = enum_policy
        self.union_policy = union_policy
        self.default_p_none = default_p_none
        self.optional_p_none = optional_p_none if optional_p_none is not None else default_p_none

    def build_model_strategies(self, model: type[BaseModel]) -> Mapping[str, StrategyResult]:
        summaries = summarize_model_fields(model)
        strategies: dict[str, StrategyResult] = {}
        for name, model_field in model.model_fields.items():
            summary = summaries[name]
            strategies[name] = self.build_field_strategy(name, model_field.annotation, summary)
        return strategies

    def build_field_strategy(
        self,
        field_name: str,
        annotation: Any,
        summary: FieldSummary,
    ) -> StrategyResult:
        base_annotation, _ = schema_module._strip_optional(annotation)
        union_args = self._extract_union_args(base_annotation)
        if union_args:
            return self._build_union_strategy(field_name, union_args)
        return self._build_single_strategy(field_name, summary, base_annotation)

    # ------------------------------------------------------------------ helpers
    def _build_union_strategy(self, field_name: str, union_args: Sequence[Any]) -> UnionStrategy:
        choices: list[Strategy] = []
        for ann in union_args:
            summary = self._summarize_inline(ann)
            choices.append(self._build_single_strategy(field_name, summary, ann))
        return UnionStrategy(field_name=field_name, choices=choices, policy=self.union_policy)

    def _build_single_strategy(
        self,
        field_name: str,
        summary: FieldSummary,
        annotation: Any,
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
            )

        provider = self.registry.get(summary.type, summary.format)
        if provider is None:
            provider = self.registry.get(summary.type)
        if provider is None and summary.type == "string":
            provider = self.registry.get("string")
        if provider is None:
            raise ValueError(
                f"No provider registered for field '{field_name}' with type '{summary.type}'."
            )

        p_none = self.default_p_none
        if summary.is_optional:
            p_none = self.optional_p_none

        strategy = Strategy(
            field_name=field_name,
            summary=summary,
            annotation=annotation,
            provider_ref=provider,
            provider_name=provider.name,
            provider_kwargs={},
            p_none=p_none,
        )
        return strategy

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


__all__ = ["Strategy", "UnionStrategy", "StrategyBuilder", "StrategyResult"]
