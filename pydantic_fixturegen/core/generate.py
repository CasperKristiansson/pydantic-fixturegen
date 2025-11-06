"""Instance generation engine using provider strategies."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import inspect
from collections.abc import Iterable, Mapping, Sized
from dataclasses import dataclass, field, is_dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, get_type_hints

from faker import Faker
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.config import ArrayConfig, ConfigError, IdentifierConfig, PathConfig
from pydantic_fixturegen.core.constraint_report import ConstraintReporter
from pydantic_fixturegen.core.field_policies import (
    FieldPolicy,
    FieldPolicyConflictError,
    FieldPolicySet,
)
from pydantic_fixturegen.core.providers import ProviderRegistry, create_default_registry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary, extract_constraints
from pydantic_fixturegen.core.seed import DEFAULT_LOCALE, SeedManager
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
    time_anchor: datetime.datetime | None = None
    field_policies: tuple[FieldPolicy, ...] = ()
    locale: str = DEFAULT_LOCALE
    locale_policies: tuple[FieldPolicy, ...] = ()
    arrays: ArrayConfig = field(default_factory=ArrayConfig)
    identifiers: IdentifierConfig = field(default_factory=IdentifierConfig)
    paths: PathConfig = field(default_factory=PathConfig)


@dataclass(slots=True)
class _PathEntry:
    module: str
    qualname: str
    via_field: str | None = None

    @property
    def full(self) -> str:
        return f"{self.module}.{self.qualname}"


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
        self.seed_manager = SeedManager(seed=self.config.seed, locale=self.config.locale)
        self.random = self.seed_manager.base_random
        self.faker = self.seed_manager.faker
        self._faker_cache: dict[tuple[str, str], Faker] = {}
        self.array_config = self.config.arrays
        self.identifier_config = self.config.identifiers
        self.path_config = self.config.paths

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
            array_config=self.array_config,
            identifier_config=self.identifier_config,
        )
        self._strategy_cache: dict[type[Any], dict[str, StrategyResult]] = {}
        self._constraint_reporter = ConstraintReporter()
        self._field_policy_set = (
            FieldPolicySet(self.config.field_policies) if self.config.field_policies else None
        )
        self._locale_policy_set = (
            FieldPolicySet(self.config.locale_policies) if self.config.locale_policies else None
        )
        self._path_stack: list[_PathEntry] = []

    @property
    def constraint_report(self) -> ConstraintReporter:
        return self._constraint_reporter

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
    def _build_model_instance(
        self,
        model_type: type[Any],
        *,
        depth: int,
        via_field: str | None = None,
    ) -> Any | None:
        if depth >= self.config.max_depth:
            return None
        if not self._consume_object():
            return None

        entry = self._make_path_entry(model_type, via_field)
        self._path_stack.append(entry)
        try:
            strategies = self._get_model_strategies(model_type)
        except TypeError:
            return None

        self._constraint_reporter.begin_model(model_type)

        values: dict[str, Any] = {}
        try:
            for field_name, strategy in strategies.items():
                self._apply_field_policies(field_name, strategy)
                values[field_name] = self._evaluate_strategy(
                    strategy,
                    depth,
                    model_type,
                    field_name,
                )
        finally:
            self._path_stack.pop()

        try:
            instance: Any | None = None
            if (isinstance(model_type, type) and issubclass(model_type, BaseModel)) or is_dataclass(
                model_type
            ):
                instance = model_type(**values)
        except ValidationError as exc:
            self._constraint_reporter.finish_model(
                model_type,
                success=False,
                errors=exc.errors(),
            )
            return None
        except Exception:
            self._constraint_reporter.finish_model(model_type, success=False)
            return None

        if instance is None:
            self._constraint_reporter.finish_model(model_type, success=False)
            return None

        self._constraint_reporter.finish_model(model_type, success=True)
        return instance

    def _evaluate_strategy(
        self,
        strategy: StrategyResult,
        depth: int,
        model_type: type[Any],
        field_name: str,
    ) -> Any:
        if isinstance(strategy, UnionStrategy):
            return self._evaluate_union(strategy, depth, model_type, field_name)
        return self._evaluate_single(strategy, depth, model_type, field_name)

    def _make_path_entry(self, model_type: type[Any], via_field: str | None) -> _PathEntry:
        module = getattr(model_type, "__module__", "<unknown>")
        qualname = getattr(
            model_type,
            "__qualname__",
            getattr(model_type, "__name__", str(model_type)),
        )
        return _PathEntry(module=module, qualname=qualname, via_field=via_field)

    def _apply_field_policies(self, field_name: str, strategy: StrategyResult) -> None:
        if self._field_policy_set is None:
            return
        full_path, aliases = self._current_field_paths(field_name)
        try:
            policy_values = self._field_policy_set.resolve(full_path, aliases=aliases)
        except FieldPolicyConflictError as exc:
            raise ConfigError(str(exc)) from exc

        if not policy_values:
            return

        if isinstance(strategy, UnionStrategy):
            union_override = policy_values.get("union_policy")
            if union_override is not None:
                strategy.policy = union_override
            element_policy = {
                key: policy_values[key]
                for key in ("p_none", "enum_policy")
                if key in policy_values and policy_values[key] is not None
            }
            if element_policy:
                for choice in strategy.choices:
                    self._apply_field_policy_to_strategy(choice, element_policy)
            return

        self._apply_field_policy_to_strategy(strategy, policy_values)

    def _current_field_paths(self, field_name: str) -> tuple[str, tuple[str, ...]]:
        if not self._path_stack:
            return field_name, ()

        full_segments: list[str] = []
        name_segments: list[str] = []
        model_segments: list[str] = []
        field_segments: list[str] = []

        for index, entry in enumerate(self._path_stack):
            if index == 0:
                full_segments.append(entry.full)
                name_segments.append(entry.qualname)
                model_segments.append(entry.qualname)
            else:
                if entry.via_field:
                    full_segments.append(entry.via_field)
                    name_segments.append(entry.via_field)
                    field_segments.append(entry.via_field)
                full_segments.append(entry.full)
                name_segments.append(entry.qualname)
                model_segments.append(entry.qualname)

        full_path = ".".join((*full_segments, field_name))

        alias_candidates: list[str] = []

        alias_candidates.append(".".join((*name_segments, field_name)))
        alias_candidates.append(".".join((*model_segments, field_name)))

        if field_segments:
            alias_candidates.append(".".join((*field_segments, field_name)))
            root_fields = ".".join((name_segments[0], *field_segments, field_name))
            alias_candidates.append(root_fields)

        last_entry = self._path_stack[-1]
        alias_candidates.append(".".join((last_entry.qualname, field_name)))
        alias_candidates.append(".".join((last_entry.full, field_name)))
        alias_candidates.append(field_name)

        aliases = self._dedupe_paths(alias_candidates, exclude=full_path)
        return full_path, aliases

    @staticmethod
    def _dedupe_paths(paths: Iterable[str], *, exclude: str) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for path in paths:
            if not path or path == exclude or path in seen:
                continue
            seen[path] = None
        return tuple(seen.keys())

    def _resolve_locale(self, field_name: str) -> tuple[str, str]:
        base_locale = self.config.locale
        full_path, aliases = self._current_field_paths(field_name)

        if self._locale_policy_set is None:
            return base_locale, full_path

        try:
            policy_values = self._locale_policy_set.resolve(full_path, aliases=aliases)
        except FieldPolicyConflictError as exc:
            raise ConfigError(str(exc)) from exc

        locale_value = policy_values.get("locale")
        return (locale_value or base_locale, full_path)

    def _faker_for_locale(self, locale: str, path_key: str) -> Faker:
        if locale == self.config.locale:
            return self.faker

        cache_key = (locale, path_key)
        if cache_key not in self._faker_cache:
            seed = self.seed_manager.derive_child_seed("faker", locale, path_key)
            faker = Faker(locale)
            faker.seed_instance(seed)
            self._faker_cache[cache_key] = faker
        return self._faker_cache[cache_key]

    def _apply_field_policy_to_strategy(
        self,
        strategy: Strategy,
        policy_values: Mapping[str, Any],
    ) -> None:
        if "p_none" in policy_values and policy_values["p_none"] is not None:
            strategy.p_none = policy_values["p_none"]
        if "enum_policy" in policy_values and policy_values["enum_policy"] is not None:
            strategy.enum_policy = policy_values["enum_policy"]

    def _evaluate_union(
        self,
        strategy: UnionStrategy,
        depth: int,
        model_type: type[Any],
        field_name: str,
    ) -> Any:
        choices = strategy.choices
        if not choices:
            return None

        selected = self.random.choice(choices) if strategy.policy == "random" else choices[0]
        return self._evaluate_single(selected, depth, model_type, field_name)

    def _evaluate_single(
        self,
        strategy: Strategy,
        depth: int,
        model_type: type[Any],
        field_name: str,
    ) -> Any:
        summary = strategy.summary
        self._constraint_reporter.record_field_attempt(model_type, field_name, summary)

        if self._should_return_none(strategy):
            value: Any = None
        else:
            enum_values = strategy.enum_values or summary.enum_values
            if enum_values:
                value = self._select_enum_value(strategy, enum_values)
            else:
                annotation = strategy.annotation

                if self._is_model_like(annotation):
                    value = self._build_model_instance(
                        annotation,
                        depth=depth + 1,
                        via_field=field_name,
                    )
                elif summary.type in {"list", "set", "tuple", "mapping"}:
                    value = self._evaluate_collection(model_type, field_name, strategy, depth)
                else:
                    if strategy.provider_ref is None:
                        value = None
                    else:
                        value = self._call_strategy_provider(model_type, field_name, strategy)

        self._constraint_reporter.record_field_value(field_name, value)
        return value

    def _evaluate_collection(
        self,
        model_type: type[Any],
        field_name: str,
        strategy: Strategy,
        depth: int,
    ) -> Any:
        summary = strategy.summary
        base_value = self._call_strategy_provider(model_type, field_name, strategy)

        item_annotation = summary.item_annotation
        if item_annotation is None or not self._is_model_like(item_annotation):
            return base_value

        if summary.type == "mapping":
            return self._build_mapping_collection(
                base_value,
                item_annotation,
                depth,
                strategy.field_name,
            )

        length = self._collection_length_from_value(base_value)
        count = max(1, length)
        items: list[Any] = []
        for _ in range(count):
            nested = self._build_model_instance(
                item_annotation,
                depth=depth + 1,
                via_field=strategy.field_name,
            )
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
        field_name: str,
    ) -> dict[str, Any]:
        if isinstance(base_value, dict) and base_value:
            keys: Iterable[str] = base_value.keys()
        else:
            length = self._collection_length_from_value(base_value)
            count = max(1, length)
            keys = (self.faker.pystr(min_chars=3, max_chars=6) for _ in range(count))

        result: dict[str, Any] = {}
        for key in keys:
            nested = self._build_model_instance(
                annotation,
                depth=depth + 1,
                via_field=field_name,
            )
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
        for field_info in dataclass_fields(cls):
            if not field_info.init:
                continue
            annotation = type_hints.get(field_info.name, field_info.type)
            summary = self._summarize_dataclass_field(field_info, annotation)
            strategies[field_info.name] = self.builder.build_field_strategy(
                cls,
                field_info.name,
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
        selection = self.random.choice(enum_values) if policy == "random" else enum_values[0]

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
        if isinstance(value, Sized):
            return len(value)
        return 0

    @staticmethod
    def _is_model_like(annotation: Any) -> bool:
        if not isinstance(annotation, type):
            return False
        try:
            return issubclass(annotation, BaseModel) or is_dataclass(annotation)
        except TypeError:
            return False

    def _call_strategy_provider(
        self,
        model_type: type[Any],
        field_name: str,
        strategy: Strategy,
    ) -> Any:
        if strategy.provider_ref is None:
            return None

        func = strategy.provider_ref.func
        locale, path_key = self._resolve_locale(field_name)
        faker = self._faker_for_locale(locale, path_key)
        numpy_rng = self.seed_manager.numpy_for("numpy-array", path_key)
        kwargs = {
            "summary": strategy.summary,
            "faker": faker,
            "random_generator": self.random,
            "time_anchor": self.config.time_anchor,
            "numpy_rng": numpy_rng,
            "path_config": self.path_config,
            "model_type": model_type,
        }
        kwargs.update(strategy.provider_kwargs)

        sig = inspect.signature(func)
        applicable = {name: value for name, value in kwargs.items() if name in sig.parameters}
        try:
            return func(**applicable)
        except Exception:
            return None


__all__ = ["InstanceGenerator", "GenerationConfig"]
