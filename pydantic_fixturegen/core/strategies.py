"""Strategy builder for field generation policies."""

from __future__ import annotations

import random
import types
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pydantic_fixturegen.core.providers import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary, summarize_model_fields
from pydantic_fixturegen.core import schema as schema_module


@dataclass(slots=True)
class Strategy:
    """Represents a concrete provider strategy for a field."""

    field_name: str
    summary: FieldSummary
    provider_name: str
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
        for name, field in model.model_fields.items():
            summary = summaries[name]
            strategies[name] = self.build_field_strategy(name, field.annotation, summary)
        return strategies

    def build_field_strategy(
        self,
        field_name: str,
        annotation: Any,
        summary: FieldSummary,
    ) -> StrategyResult:
        base_annotation, _ = self._strip_optional(annotation)
        union_args = self._extract_union_args(base_annotation)
        if union_args:
            return self._build_union_strategy(field_name, union_args)
        return self._build_single_strategy(field_name, summary)

    # ------------------------------------------------------------------ helpers
    def _build_union_strategy(self, field_name: str, union_args: Sequence[Any]) -> UnionStrategy:
        choices: list[Strategy] = []
        for ann in union_args:
            summary = self._summarize_inline(ann)
            choices.append(self._build_single_strategy(field_name, summary))
        return UnionStrategy(field_name=field_name, choices=choices, policy=self.union_policy)

    def _build_single_strategy(self, field_name: str, summary: FieldSummary) -> Strategy:
        if summary.enum_values:
            return Strategy(
                field_name=field_name,
                summary=summary,
                provider_name="enum.static",
                provider_kwargs={},
                p_none=self.optional_p_none if summary.is_optional else self.default_p_none,
                enum_values=summary.enum_values,
                enum_policy=self.enum_policy,
            )

        provider = self.registry.get(summary.type, summary.format)
        if provider is None:
            provider = self.registry.get(summary.type)
        if provider is None and summary.type == "string":
            provider = self.registry.get("string")
        if provider is None:
            raise ValueError(f"No provider registered for field '{field_name}' with type '{summary.type}'.")

        p_none = self.default_p_none
        if summary.is_optional:
            p_none = self.optional_p_none

        strategy = Strategy(
            field_name=field_name,
            summary=summary,
            provider_name=provider.name,
            provider_kwargs={},
            p_none=p_none,
        )

        if summary.enum_values:
            strategy.enum_values = summary.enum_values
            strategy.enum_policy = self.enum_policy

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
        inner, is_optional = schema_module._strip_optional(annotation)
        type_name, fmt, item_ann = schema_module._infer_annotation_kind(inner)
        item_type = None
        if item_ann is not None:
            item_type, _, _ = schema_module._infer_annotation_kind(item_ann)
        enum_values = schema_module._extract_enum_values(inner)
        return FieldSummary(
            type=type_name,
            constraints=FieldConstraints(),
            format=fmt,
            item_type=item_type,
            enum_values=enum_values,
            is_optional=is_optional,
        )

    @staticmethod
    def _strip_optional(annotation: Any) -> tuple[Any, bool]:
        origin = get_origin(annotation)
        if origin in {Union, types.UnionType}:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]  # noqa: E721
            if len(args) == 1 and len(get_args(annotation)) != len(args):
                return args[0], True
        return annotation, False


__all__ = ["Strategy", "UnionStrategy", "StrategyBuilder", "StrategyResult"]
