"""Instance generation engine using provider strategies."""

from __future__ import annotations

import dataclasses
import enum
import inspect
import random
from collections.abc import Iterable
from dataclasses import dataclass, is_dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, get_type_hints

from faker import Faker
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.providers import ProviderRegistry, create_default_registry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary, extract_constraints
from pydantic_fixturegen.core.strategies import (
    Strategy,
    StrategyBuilder,
    StrategyResult,
    UnionStrategy,
)
from pydantic_fixturegen.plugins.loader import get_plugin_manager, load_entrypoint_plugins


@dataclass(slots=True)
class GenerationConfig:
    max_depth: int = 5
    max_objects: int = 100
    enum_policy: str = "first"
    union_policy: str = "first"
    default_p_none: float = 0.0
    optional_p_none: float = 0.0
    seed: int | None = None


class InstanceGenerator:
    """Generate instances of Pydantic models with recursion guards."""

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        config: GenerationConfig | None = None,
    ) -> None:
        self.config = config or GenerationConfig()
        self.registry = registry or create_default_registry(load_plugins=False)
        self.random = random.Random(self.config.seed)
        self.faker = Faker()
        if self.config.seed is not None:
            Faker.seed(self.config.seed)
            self.faker.seed_instance(self.config.seed)

        load_entrypoint_plugins()
        self._plugin_manager = get_plugin_manager()

        if registry is None:
            self.registry.load_entrypoint_plugins()

        self.builder = StrategyBuilder(
            self.registry,
            enum_policy=self.config.enum_policy,
            union_policy=self.config.union_policy,
            default_p_none=self.config.default_p_none,
            optional_p_none=self.config.optional_p_none,
            plugin_manager=self._plugin_manager,
        )
        self._strategy_cache: dict[type[Any], dict[str, StrategyResult]] = {}

    # ------------------------------------------------------------------ public API
    def generate_one(self, model: type[BaseModel]) -> BaseModel | None:
        self._objects_remaining = self.config.max_objects
        return self._build_model_instance(model, depth=0)

    def generate(self, model: type[BaseModel], count: int = 1) -> list[BaseModel]:
        results: list[BaseModel] = []
        for _ in range(count):
            instance = self.generate_one(model)
            if instance is None:
                break
            results.append(instance)
        return results

    # ------------------------------------------------------------------ internals
    def _build_model_instance(self, model_type: type[Any], *, depth: int) -> Any | None:
        if depth >= self.config.max_depth:
            return None
        if not self._consume_object():
            return None

        try:
            strategies = self._get_model_strategies(model_type)
        except TypeError:
            return None

        values: dict[str, Any] = {}
        for field_name, strategy in strategies.items():
            values[field_name] = self._evaluate_strategy(strategy, depth)

        try:
            if isinstance(model_type, type) and issubclass(model_type, BaseModel):
                return model_type(**values)
            if is_dataclass(model_type):
                return model_type(**values)
        except Exception:
            return None
        return None

    def _evaluate_strategy(self, strategy: StrategyResult, depth: int) -> Any:
        if isinstance(strategy, UnionStrategy):
            return self._evaluate_union(strategy, depth)
        return self._evaluate_single(strategy, depth)

    def _evaluate_union(self, strategy: UnionStrategy, depth: int) -> Any:
        choices = strategy.choices
        if not choices:
            return None

        selected = (
            self.random.choice(choices)
            if strategy.policy == "random"
            else choices[0]
        )
        return self._evaluate_single(selected, depth)

    def _evaluate_single(self, strategy: Strategy, depth: int) -> Any:
        if self._should_return_none(strategy):
            return None

        summary = strategy.summary
        enum_values = strategy.enum_values or summary.enum_values

        if enum_values:
            return self._select_enum_value(strategy, enum_values)

        annotation = strategy.annotation

        if self._is_model_like(annotation):
            return self._build_model_instance(annotation, depth=depth + 1)

        if summary.type in {"list", "set", "tuple", "mapping"}:
            return self._evaluate_collection(strategy, depth)

        if strategy.provider_ref is None:
            return None
        return self._call_strategy_provider(strategy)

    def _evaluate_collection(self, strategy: Strategy, depth: int) -> Any:
        summary = strategy.summary
        base_value = self._call_strategy_provider(strategy)

        item_annotation = summary.item_annotation
        if item_annotation is None or not self._is_model_like(item_annotation):
            return base_value

        if summary.type == "mapping":
            return self._build_mapping_collection(base_value, item_annotation, depth)

        length = self._collection_length_from_value(base_value)
        count = max(1, length)
        items: list[Any] = []
        for _ in range(count):
            nested = self._build_model_instance(item_annotation, depth=depth + 1)
            if nested is not None:
                items.append(nested)

        if summary.type == "list":
            return items
        if summary.type == "tuple":
            return tuple(items)
        if summary.type == "set":
            try:
                return set(items)
            except TypeError:
                return set()
        return base_value

    def _build_mapping_collection(
        self,
        base_value: Any,
        annotation: Any,
        depth: int,
    ) -> dict[str, Any]:
        if isinstance(base_value, dict) and base_value:
            keys: Iterable[str] = base_value.keys()
        else:
            length = self._collection_length_from_value(base_value)
            count = max(1, length)
            keys = (self.faker.pystr(min_chars=3, max_chars=6) for _ in range(count))

        result: dict[str, Any] = {}
        for key in keys:
            nested = self._build_model_instance(annotation, depth=depth + 1)
            if nested is not None:
                result[str(key)] = nested
        return result

    def _consume_object(self) -> bool:
        if getattr(self, "_objects_remaining", 0) <= 0:
            return False
        self._objects_remaining -= 1
        return True

    def _get_model_strategies(self, model_type: type[Any]) -> dict[str, StrategyResult]:
        cached = self._strategy_cache.get(model_type)
        if cached is not None:
            return cached

        if isinstance(model_type, type) and issubclass(model_type, BaseModel):
            strategies = dict(self.builder.build_model_strategies(model_type))
        elif is_dataclass(model_type):
            strategies = self._build_dataclass_strategies(model_type)
        else:
            raise TypeError(f"Unsupported model type: {model_type!r}")

        self._strategy_cache[model_type] = strategies
        return strategies

    def _build_dataclass_strategies(self, cls: type[Any]) -> dict[str, StrategyResult]:
        strategies: dict[str, StrategyResult] = {}
        type_hints = get_type_hints(cls)
        for field in dataclass_fields(cls):
            if not field.init:
                continue
            annotation = type_hints.get(field.name, field.type)
            summary = self._summarize_dataclass_field(field, annotation)
            strategies[field.name] = self.builder.build_field_strategy(
                cls,
                field.name,
                annotation,
                summary,
            )
        return strategies

    def _summarize_dataclass_field(
        self,
        field: dataclasses.Field[Any],
        annotation: Any,
    ) -> FieldSummary:
        field_info = self._extract_field_info(field)
        if field_info is not None:
            constraints = extract_constraints(field_info)
        else:
            constraints = FieldConstraints()
        return schema_module._summarize_annotation(annotation, constraints)

    @staticmethod
    def _extract_field_info(field: dataclasses.Field[Any]) -> FieldInfo | None:
        for meta in getattr(field, "metadata", ()):
            if isinstance(meta, FieldInfo):
                return meta
        return None

    def _should_return_none(self, strategy: Strategy) -> bool:
        if strategy.p_none <= 0:
            return False
        return self.random.random() < strategy.p_none

    def _select_enum_value(self, strategy: Strategy, enum_values: list[Any]) -> Any:
        if not enum_values:
            return None

        policy = strategy.enum_policy or self.config.enum_policy
        selection = (
            self.random.choice(enum_values)
            if policy == "random"
            else enum_values[0]
        )

        annotation = strategy.annotation
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            try:
                return annotation(selection)
            except Exception:
                return selection
        return selection

    @staticmethod
    def _collection_length_from_value(value: Any) -> int:
        if value is None:
            return 0
        try:
            return len(value)  # type: ignore[arg-type]
        except TypeError:
            return 0

    @staticmethod
    def _is_model_like(annotation: Any) -> bool:
        if not isinstance(annotation, type):
            return False
        try:
            return issubclass(annotation, BaseModel) or is_dataclass(annotation)
        except TypeError:
            return False

    def _call_strategy_provider(self, strategy: Strategy) -> Any:
        if strategy.provider_ref is None:
            return None

        func = strategy.provider_ref.func
        kwargs = {
            "summary": strategy.summary,
            "faker": self.faker,
            "random_generator": self.random,
        }
        kwargs.update(strategy.provider_kwargs)

        sig = inspect.signature(func)
        applicable = {name: value for name, value in kwargs.items() if name in sig.parameters}
        try:
            return func(**applicable)
        except Exception:
            return None


__all__ = ["InstanceGenerator", "GenerationConfig"]
