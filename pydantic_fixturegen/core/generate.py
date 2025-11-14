"""Instance generation engine using provider strategies."""

from __future__ import annotations

import copy
import dataclasses
import datetime
import enum
import fnmatch
import importlib
import inspect
import random
from collections.abc import Callable, Iterable, Mapping, Sequence, Sized
from dataclasses import dataclass, field, is_dataclass
from typing import Any, cast

from faker import Faker
from pydantic import BaseModel, TypeAdapter, ValidationError

from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.collection_utils import sample_collection_length
from pydantic_fixturegen.core.config import (
    ArrayConfig,
    CollectionConfig,
    ConfigError,
    FieldHintConfig,
    FieldHintModeLiteral,
    IdentifierConfig,
    NumberDistributionConfig,
    PathConfig,
    ProviderDefaultsConfig,
    RelationLinkConfig,
)
from pydantic_fixturegen.core.constraint_report import ConstraintReporter
from pydantic_fixturegen.core.cycle_report import CycleEvent, attach_cycle_events
from pydantic_fixturegen.core.field_policies import (
    FieldPolicy,
    FieldPolicyConflictError,
    FieldPolicySet,
)
from pydantic_fixturegen.core.model_utils import is_typeddict_type
from pydantic_fixturegen.core.overrides import (
    FieldOverride,
    FieldOverrideContext,
    FieldOverrideSet,
)
from pydantic_fixturegen.core.providers import (
    ProviderRef,
    ProviderRegistry,
    create_default_registry,
)
from pydantic_fixturegen.core.schema import FieldSummary
from pydantic_fixturegen.core.seed import DEFAULT_LOCALE, RNGModeLiteral, SeedManager
from pydantic_fixturegen.core.seed_freeze import canonical_module_name
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
    collections: CollectionConfig = field(default_factory=CollectionConfig)
    identifiers: IdentifierConfig = field(default_factory=IdentifierConfig)
    numbers: NumberDistributionConfig = field(default_factory=NumberDistributionConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    field_hints: FieldHintConfig = field(default_factory=FieldHintConfig)
    provider_defaults: ProviderDefaultsConfig = field(default_factory=ProviderDefaultsConfig)
    respect_validators: bool = False
    validator_max_retries: int = 2
    relations: tuple[RelationLinkConfig, ...] = ()
    relation_models: Mapping[str, type[Any]] = field(default_factory=dict)
    cycle_policy: str = "reuse"
    rng_mode: RNGModeLiteral = "portable"
    heuristics_enabled: bool = True
    field_overrides: FieldOverrideSet | None = None


@dataclass(slots=True)
class _PathEntry:
    module: str
    qualname: str
    model_type: type[Any]
    via_field: str | None = None
    path: str | None = None
    partial_values: dict[str, Any] = field(default_factory=dict)

    @property
    def full(self) -> str:
        if self.path:
            return self.path
        return f"{self.module}.{self.qualname}"


_RELATION_SKIP = object()
_PENDING_FAILURE_NONE = object()
_HINT_UNSET = object()


@dataclass(slots=True)
class _RelationBinding:
    source_keys: tuple[str, ...]
    target_model: str
    target_simple: str
    target_field: str


ModelDelegate = Callable[["InstanceGenerator", type[Any], str], Any | None]


def _simple_name(identifier: str) -> str:
    parts = identifier.split(".")
    return parts[-1] if parts else identifier


def _split_endpoint(endpoint: str) -> tuple[str, str]:
    text = endpoint.strip()
    if not text or "." not in text:
        raise ConfigError("relation endpoints must be formatted as 'Model.field'.")
    model, field = text.rsplit(".", 1)
    model = model.strip()
    field = field.strip()
    if not model or not field:
        raise ConfigError("relation endpoints must include both model and field names.")
    return model, field


class RelationManager:
    def __init__(
        self,
        links: tuple[RelationLinkConfig, ...],
        model_lookup: Mapping[str, type[Any]] | None,
    ) -> None:
        self._bindings: dict[str, _RelationBinding] = {}
        self._model_lookup: dict[str, type[Any]] = {}
        if model_lookup:
            for key, model in model_lookup.items():
                self._model_lookup[key] = model
        self._buckets: dict[str, list[Any]] = {}

        for link in links:
            binding = self._build_binding(link)
            for key in binding.source_keys:
                if key in self._bindings:
                    continue
                self._bindings[key] = binding

    def _build_binding(self, link: RelationLinkConfig) -> _RelationBinding:
        source_model, source_field = _split_endpoint(link.source)
        target_model, target_field = _split_endpoint(link.target)
        simple_source = _simple_name(source_model)
        simple_target = _simple_name(target_model)
        source_keys = {f"{source_model}.{source_field}"}
        source_keys.add(f"{simple_source}.{source_field}")
        return _RelationBinding(
            source_keys=tuple(source_keys),
            target_model=target_model,
            target_simple=simple_target,
            target_field=target_field,
        )

    def register_instance(self, model_type: type[Any], instance: Any) -> None:
        key_full = InstanceGenerator._describe_model(model_type)
        key_simple = _simple_name(key_full)
        bucket = self._buckets.get(key_full)
        if bucket is None:
            bucket = []
            self._buckets[key_full] = bucket
        self._buckets[key_simple] = bucket
        bucket.append(instance)

    def resolve_value(
        self,
        *,
        model_keys: Iterable[str],
        field_name: str,
        generator: InstanceGenerator,
        depth: int,
    ) -> Any:
        candidates: list[str] = []
        for key in model_keys:
            if not key:
                continue
            candidates.append(f"{key}.{field_name}")

        for candidate in candidates:
            binding = self._bindings.get(candidate)
            if binding is None:
                continue
            value = self._resolve_binding(binding, generator, depth)
            if value is not _RELATION_SKIP:
                return value
        return _RELATION_SKIP

    def _resolve_binding(
        self,
        binding: _RelationBinding,
        generator: InstanceGenerator,
        depth: int,
    ) -> Any:
        bucket = self._buckets.get(binding.target_model) or self._buckets.get(binding.target_simple)
        if not bucket:
            target_cls = self._model_lookup.get(binding.target_model) or self._model_lookup.get(
                binding.target_simple
            )
            if target_cls is None:
                target_cls = self._import_model(binding.target_model)
            if target_cls is None:
                target_cls = self._import_model(binding.target_simple)
            if target_cls is None:
                return _RELATION_SKIP
            instance = generator._build_model_instance(target_cls, depth=depth + 1)
            if instance is None:
                return None
            self.register_instance(target_cls, instance)
            bucket = self._buckets.get(binding.target_model)
        if not bucket:
            return None
        target_instance = bucket[-1]
        return getattr(target_instance, binding.target_field, None)

    def _import_model(self, dotted: str) -> type[Any] | None:
        if "." not in dotted:
            return None
        module_name, attr_name = dotted.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
        except Exception:  # pragma: no cover - defensive import failure
            return None
        candidate = getattr(module, attr_name, None)
        if not isinstance(candidate, type):
            return None
        self._model_lookup[dotted] = candidate
        simple = _simple_name(dotted)
        self._model_lookup.setdefault(simple, candidate)
        return candidate


class FieldHintResolver:
    """Resolves hint modes (defaults/examples) per model."""

    def __init__(self, config: FieldHintConfig) -> None:
        self._default_mode: FieldHintModeLiteral = config.mode
        self._overrides: tuple[tuple[str, FieldHintModeLiteral], ...] = config.model_modes
        self.enabled = self._default_mode != "none" or bool(self._overrides)

    def mode_for(self, model_keys: Sequence[str]) -> FieldHintModeLiteral:
        for pattern, mode in self._overrides:
            for key in model_keys:
                if fnmatch.fnmatchcase(key, pattern):
                    return mode
        return self._default_mode


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
        self.seed_manager = SeedManager(
            seed=self.config.seed,
            locale=self.config.locale,
            rng_mode=self.config.rng_mode,
        )
        self.random = self.seed_manager.base_random
        self.faker = self.seed_manager.faker
        self._faker_cache: dict[tuple[str, str, tuple[Any, ...] | None], Faker] = {}
        self.array_config = self.config.arrays
        self.collection_config = self.config.collections
        self.identifier_config = self.config.identifiers
        self.number_config = self.config.numbers
        self.path_config = self.config.paths
        if self.config.validator_max_retries < 0:
            raise ValueError("validator_max_retries must be >= 0.")
        self._validator_retry_enabled = bool(self.config.respect_validators)
        self._last_validator_failure: dict[str, Any] | None = None
        self._pending_validator_failure: dict[str, Any] | object = _PENDING_FAILURE_NONE
        self._retry_stream_state: tuple[random.Random, Faker] | None = None
        self._retry_seed_token: tuple[Any, ...] | None = None
        self._relation_manager = (
            RelationManager(self.config.relations, self.config.relation_models)
            if self.config.relations
            else None
        )
        self._field_hint_resolver: FieldHintResolver | None = None
        self._field_hint_mode_cache: dict[type[Any], FieldHintModeLiteral] = {}
        if self.config.field_hints.mode != "none" or self.config.field_hints.model_modes:
            resolver = FieldHintResolver(self.config.field_hints)
            if resolver.enabled:
                self._field_hint_resolver = resolver

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
            number_config=self.number_config,
            heuristics_enabled=self.config.heuristics_enabled,
            cycle_policy=self.config.cycle_policy,
            provider_defaults=self.config.provider_defaults,
        )
        self._strategy_cache: dict[type[Any], dict[str, StrategyResult]] = {}
        self._constraint_reporter = ConstraintReporter()
        self._field_policy_set = (
            FieldPolicySet(self.config.field_policies) if self.config.field_policies else None
        )
        self._locale_policy_set = (
            FieldPolicySet(self.config.locale_policies) if self.config.locale_policies else None
        )
        self._field_override_set = self.config.field_overrides
        self._override_cache: dict[tuple[type[Any], str], FieldOverride | None] = {}
        self._path_stack: list[_PathEntry] = []
        self._cycle_policy = self.config.cycle_policy
        self._cycle_events: list[CycleEvent] = []
        self._reuse_pool: dict[type[Any], list[tuple[str, BaseModel]]] = {}
        self._delegated_models: dict[type[Any], ModelDelegate] = {}
        self._last_generation_failure: dict[str, Any] | None = None

    @property
    def constraint_report(self) -> ConstraintReporter:
        return self._constraint_reporter

    @property
    def generation_failure_details(self) -> dict[str, Any] | None:
        return self._last_generation_failure

    # ------------------------------------------------------------------ public API
    def generate_one(self, model: type[Any]) -> Any | None:
        self._objects_remaining = self.config.max_objects
        self._cycle_events = []
        instance = self._generate_with_retries(
            model,
            depth=0,
        )
        if instance is not None:
            attach_cycle_events(instance, self._cycle_events)
            self._cycle_events = []
        return instance

    def generate(self, model: type[Any], count: int = 1) -> list[Any]:
        results: list[Any] = []
        for _ in range(count):
            instance = self.generate_one(model)
            if instance is None:
                break
            results.append(instance)
        return results

    def _activate_validator_retry(self, model_type: type[Any], attempt_index: int) -> None:
        model_key = self._describe_model(model_type)
        token = (model_key, attempt_index)
        self._retry_seed_token = token
        self._retry_stream_state = (self.random, self.faker)
        self.random = self.seed_manager.random_for("validator_retry", *token)
        self.faker = self.seed_manager.faker_for("validator_retry", *token)

    def _restore_validator_retry(self) -> None:
        if self._retry_stream_state is None:
            return
        self.random, self.faker = self._retry_stream_state
        self._retry_stream_state = None
        self._retry_seed_token = None

    @property
    def validator_failure_details(self) -> dict[str, Any] | None:
        return self._last_validator_failure

    def _generate_with_retries(
        self,
        model: type[Any],
        *,
        depth: int,
    ) -> Any | None:
        max_attempts = 1
        if self._validator_retry_enabled:
            max_attempts = max(1, self.config.validator_max_retries + 1)

        last_failure: dict[str, Any] | None = None
        self._last_generation_failure = None
        for attempt_index in range(max_attempts):
            if self._validator_retry_enabled:
                self._activate_validator_retry(model, attempt_index)
            objects_snapshot = self._objects_remaining
            self._pending_validator_failure = _PENDING_FAILURE_NONE
            result = self._build_model_instance(
                model,
                depth=depth,
                current_path=self._describe_model(model),
            )
            if self._validator_retry_enabled:
                self._restore_validator_retry()
            if result is not None:
                self._last_validator_failure = None
                return result

            pending_failure = self._pending_validator_failure
            self._pending_validator_failure = _PENDING_FAILURE_NONE
            failure = pending_failure if isinstance(pending_failure, dict) else None
            if failure is not None:
                failure["attempt"] = attempt_index + 1
                failure["max_attempts"] = max_attempts
                last_failure = failure

            if (
                not self._validator_retry_enabled
                or failure is None
                or attempt_index + 1 >= max_attempts
            ):
                break

            self._objects_remaining = objects_snapshot

        self._last_validator_failure = last_failure
        return None

    # ------------------------------------------------------------------ internals
    def _build_model_instance(
        self,
        model_type: type[Any],
        *,
        depth: int,
        via_field: str | None = None,
        current_path: str | None = None,
    ) -> Any | None:
        path_label = current_path or self._describe_model(model_type)
        if depth >= self.config.max_depth:
            return self._handle_cycle_resolution(
                model_type,
                path_label,
                reason="max_depth",
                ref_entry=None,
            )

        cycle_entry = self._detect_cycle_entry(model_type)
        if cycle_entry is not None:
            return self._handle_cycle_resolution(
                model_type,
                path_label,
                reason="cycle",
                ref_entry=cycle_entry,
            )

        if not self._consume_object():
            self._note_generation_failure("object_budget_exhausted", path=path_label)
            return None

        entry = self._make_path_entry(model_type, via_field, path=path_label)
        self._path_stack.append(entry)
        try:
            strategies = self._get_model_strategies(model_type)
        except TypeError as exc:
            self._note_generation_failure(
                "strategy_error",
                path=path_label,
                error=str(exc),
                model=self._describe_model(model_type),
            )
            self._path_stack.pop()
            return None

        report_model: type[Any] | None = None
        if isinstance(model_type, type):
            report_model = cast(type[Any], model_type)
            self._constraint_reporter.begin_model(report_model)

        delegate = self._delegated_models.get(model_type)
        if delegate is not None:
            delegated_instance = self._run_delegate(
                delegate,
                model_type,
                path_label,
                report_model,
            )
            self._path_stack.pop()
            return delegated_instance

        values: dict[str, Any] = {}
        post_actions: list[tuple[str, FieldOverride, FieldOverrideContext]] = []
        try:
            for field_name, strategy in strategies.items():
                override = self._field_override(model_type, field_name)
                if override and override.ignore:
                    continue

                summary = self._strategy_summary(strategy)
                context: FieldOverrideContext | None = None
                if override and override.has_value_override:
                    context = self._build_override_context(
                        model_type,
                        field_name,
                        summary,
                        values,
                        entry,
                    )
                    value = override.resolve_value(context)
                else:
                    if override and override.require:
                        full_path = f"{entry.full}.{field_name}"
                        raise ConfigError(
                            f"Override '{full_path}' is marked as require; provide a value via "
                            "config or CLI overrides."
                        )
                    hint_value = _HINT_UNSET
                    if override is None:
                        hint_value = self._maybe_apply_field_hint(model_type, summary)
                    if hint_value is not _HINT_UNSET:
                        value = hint_value
                    else:
                        self._apply_field_policies(field_name, strategy)
                        value = self._evaluate_strategy(
                            strategy,
                            depth,
                            model_type,
                            field_name,
                            report_model,
                        )
                values[field_name] = value
                entry.partial_values[field_name] = value
                if override and override.post_generate:
                    if context is None:
                        context = self._build_override_context(
                            model_type,
                            field_name,
                            summary,
                            values,
                            entry,
                        )
                    post_actions.append((field_name, override, context))
        finally:
            self._path_stack.pop()

        for field_name, override, context in post_actions:
            updated = override.apply_post(values.get(field_name), context)
            values[field_name] = updated
            entry.partial_values[field_name] = updated

        try:
            instance: Any | None = None
            if (
                self._is_pydantic_model_type(model_type)
                or is_dataclass(model_type)
                or is_typeddict_type(model_type)
            ):
                instance = model_type(**values)
        except ValidationError as exc:
            self._record_validator_failure(
                model_type,
                values,
                message=str(exc),
                errors=exc.errors(),
            )
            if report_model is not None:
                self._constraint_reporter.finish_model(
                    report_model,
                    success=False,
                    errors=exc.errors(),
                )
            return None
        except Exception as exc:
            self._record_validator_failure(
                model_type,
                values,
                message=str(exc),
                errors=(
                    {
                        "loc": ["__root__"],
                        "msg": str(exc),
                        "type": exc.__class__.__name__,
                    },
                ),
            )
            if report_model is not None:
                self._constraint_reporter.finish_model(report_model, success=False)
            return None

        if instance is None:
            self._note_generation_failure("constructor_returned_none", path=path_label)
            if report_model is not None:
                self._constraint_reporter.finish_model(report_model, success=False)
            return None

        if report_model is not None:
            self._constraint_reporter.finish_model(report_model, success=True)
        self._register_reusable_instance(model_type, path_label, instance)
        if (
            instance is not None
            and self._relation_manager is not None
            and isinstance(model_type, type)
        ):
            self._relation_manager.register_instance(model_type, instance)
        return instance

    def register_delegate(self, model_type: type[Any], delegate: ModelDelegate) -> None:
        """Register a delegate that overrides generation for ``model_type``."""

        self._delegated_models[model_type] = delegate

    def _run_delegate(
        self,
        delegate: ModelDelegate,
        model_type: type[Any],
        path_label: str,
        report_model: type[Any] | None,
    ) -> Any | None:
        try:
            instance = delegate(self, model_type, path_label)
        except Exception as exc:  # pragma: no cover - defensive delegate failure
            self._record_validator_failure(
                model_type,
                {},
                message=f"Delegate for {path_label} failed: {exc}",
                errors=(
                    {
                        "loc": [path_label],
                        "msg": str(exc),
                        "type": exc.__class__.__name__,
                    },
                ),
            )
            if report_model is not None:
                self._constraint_reporter.finish_model(report_model, success=False)
            return None

        if instance is None:
            self._note_generation_failure(
                "delegate_returned_none",
                path=path_label,
                delegate=getattr(delegate, "__qualname__", repr(delegate)),
            )
            if report_model is not None:
                self._constraint_reporter.finish_model(report_model, success=False)
            return None

        if report_model is not None:
            self._constraint_reporter.finish_model(report_model, success=True)
        self._register_reusable_instance(model_type, path_label, instance)
        if (
            instance is not None
            and self._relation_manager is not None
            and isinstance(model_type, type)
        ):
            self._relation_manager.register_instance(model_type, instance)
        return instance

    def _evaluate_strategy(
        self,
        strategy: StrategyResult,
        depth: int,
        model_type: type[Any],
        field_name: str,
        report_model: type[Any] | None,
    ) -> Any:
        if isinstance(strategy, UnionStrategy):
            return self._evaluate_union(strategy, depth, model_type, field_name, report_model)
        return self._evaluate_single(strategy, depth, model_type, field_name, report_model)

    def _make_path_entry(
        self,
        model_type: type[Any],
        via_field: str | None,
        *,
        path: str | None,
    ) -> _PathEntry:
        module = canonical_module_name(model_type)
        qualname = getattr(
            model_type,
            "__qualname__",
            getattr(model_type, "__name__", str(model_type)),
        )
        return _PathEntry(
            module=module,
            qualname=qualname,
            model_type=model_type,
            via_field=via_field,
            path=path,
        )

    @staticmethod
    def _describe_model(model_type: type[Any]) -> str:
        module = canonical_module_name(model_type)
        qualname = getattr(
            model_type,
            "__qualname__",
            getattr(model_type, "__name__", str(model_type)),
        )
        return f"{module}.{qualname}"

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

    def _apply_override_to_strategy(
        self,
        model_type: type[Any],
        field_name: str,
        strategy: StrategyResult,
        override: FieldOverride,
    ) -> None:
        path = f"{self._describe_model(model_type)}.{field_name}"
        if isinstance(strategy, UnionStrategy):
            if override.union_policy is not None:
                strategy.policy = override.union_policy
            disallowed = any(
                (
                    override.provider,
                    override.provider_format,
                    bool(override.provider_kwargs),
                    override.p_none is not None,
                    override.enum_policy,
                )
            )
            if disallowed:
                raise ConfigError(
                    f"Override '{path}' cannot override providers or probabilities on union fields."
                )
            return

        if override.provider is not None or override.provider_format is not None:
            provider = self._resolve_override_provider(path, strategy, override)
            strategy.provider_ref = provider
            strategy.provider_name = provider.name
        if override.provider_kwargs:
            strategy.provider_kwargs.update(dict(override.provider_kwargs))
        if override.p_none is not None:
            strategy.p_none = override.p_none
        if override.enum_policy is not None and strategy.enum_values:
            strategy.enum_policy = override.enum_policy
        if override.union_policy is not None:
            raise ConfigError(
                f"Override '{path}' specifies union_policy but the field is not a union."
            )

    def _resolve_override_provider(
        self,
        path: str,
        strategy: Strategy,
        override: FieldOverride,
    ) -> ProviderRef:
        type_id = override.provider or strategy.summary.type
        format_id = override.provider_format or strategy.summary.format
        if type_id is None:
            raise ConfigError(f"Override '{path}' must specify a provider type.")
        provider = self.registry.get(type_id, format_id)
        if provider is None:
            if format_id is not None:
                raise ConfigError(
                    f"Override '{path}' references unknown provider '{type_id}'"
                    f" with format '{format_id}'."
                )
            raise ConfigError(f"Override '{path}' references unknown provider '{type_id}'.")
        return provider

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

        # Allow model-level policies (with or without module prefixes) by matching
        # the current path entries directly, not only field-qualified variants.
        for entry in self._path_stack:
            alias_candidates.append(entry.qualname)
            alias_candidates.append(entry.full)

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

    def _field_override(self, model_type: type[Any], field_name: str) -> FieldOverride | None:
        if self._field_override_set is None:
            return None
        cache_key = (model_type, field_name)
        if cache_key in self._override_cache:
            return self._override_cache[cache_key]

        model_keys = self._model_identifier_keys(model_type)
        alias = self._field_alias(model_type, field_name)
        aliases = (alias,) if alias else None
        override = self._field_override_set.resolve(
            model_keys=model_keys,
            field_name=field_name,
            aliases=aliases,
        )
        self._override_cache[cache_key] = override
        return override

    def _model_identifier_keys(self, model_type: type[Any]) -> tuple[str, ...]:
        full = self._describe_model(model_type)
        qualname = getattr(model_type, "__qualname__", "")
        name = getattr(model_type, "__name__", "")
        simple = _simple_name(full)
        candidates = [full]
        for candidate in (qualname, name, simple):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return tuple(candidates)

    def _field_alias(self, model_type: type[Any], field_name: str) -> str | None:
        model_fields = getattr(model_type, "model_fields", None)
        if not isinstance(model_fields, Mapping):
            return None
        field_info = model_fields.get(field_name)
        if field_info is None:
            return None
        alias = getattr(field_info, "alias", None)
        if isinstance(alias, str) and alias != field_name:
            return alias
        return None

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

        cache_key = (locale, path_key, self._retry_seed_token)
        if cache_key not in self._faker_cache:
            seed_parts: list[Any] = ["faker", locale, path_key]
            if self._retry_seed_token is not None:
                seed_parts.extend(self._retry_seed_token)
            seed = self.seed_manager.derive_child_seed(*seed_parts)
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
        if "union_policy" in policy_values and policy_values["union_policy"] is not None:
            strategy.union_policy = policy_values["union_policy"]

        min_override = policy_values.get("collection_min_items")
        max_override = policy_values.get("collection_max_items")
        distribution_override = policy_values.get("collection_distribution")

        if (
            min_override is not None
            or max_override is not None
            or distribution_override is not None
        ):
            base_config = strategy.collection_config or self.collection_config
            if base_config is None:
                base_config = CollectionConfig()

            min_items = base_config.min_items
            max_items = base_config.max_items
            distribution = base_config.distribution

            if min_override is not None:
                min_items = max(0, int(min_override))
            if max_override is not None:
                max_items = max(0, int(max_override))
            if max_items < min_items:
                max_items = min_items
            if distribution_override is not None:
                candidate = str(distribution_override).strip().lower()
                if candidate in {"uniform", "min-heavy", "max-heavy"}:
                    distribution = candidate  # type: ignore[assignment]

            strategy.collection_config = CollectionConfig(
                min_items=min_items,
                max_items=max_items,
                distribution=distribution,
            )
            strategy.provider_kwargs.setdefault(
                "collection_config",
                strategy.collection_config,
            )

    def _maybe_apply_field_hint(
        self,
        model_type: type[Any],
        summary: FieldSummary | None,
    ) -> Any:
        if summary is None or self._field_hint_resolver is None:
            return _HINT_UNSET
        mode = self._get_field_hint_mode(model_type)
        if mode == "none":
            return _HINT_UNSET
        for preference in self._hint_order(mode):
            if preference == "examples":
                value = self._hint_value_from_examples(summary)
            else:
                value = self._hint_value_from_defaults(summary)
            if value is not _HINT_UNSET:
                return value
        return _HINT_UNSET

    def _get_field_hint_mode(self, model_type: type[Any]) -> FieldHintModeLiteral:
        cached = self._field_hint_mode_cache.get(model_type)
        if cached is not None:
            return cached
        if self._field_hint_resolver is None:
            return "none"
        model_keys = self._model_identifier_keys(model_type)
        mode = self._field_hint_resolver.mode_for(model_keys)
        self._field_hint_mode_cache[model_type] = mode
        return mode

    @staticmethod
    def _hint_order(mode: FieldHintModeLiteral) -> tuple[str, ...]:
        if mode == "defaults":
            return ("defaults",)
        if mode == "examples":
            return ("examples",)
        if mode == "defaults-then-examples":
            return ("defaults", "examples")
        if mode == "examples-then-defaults":
            return ("examples", "defaults")
        return ()

    def _hint_value_from_defaults(self, summary: FieldSummary) -> Any:
        if summary.has_default:
            return self._clone_hint_value(summary.default_value)
        if summary.default_factory is not None:
            try:
                generated = summary.default_factory()
            except Exception:
                return _HINT_UNSET
            return self._clone_hint_value(generated)
        return _HINT_UNSET

    def _hint_value_from_examples(self, summary: FieldSummary) -> Any:
        if not summary.examples:
            return _HINT_UNSET
        example = summary.examples[0]
        return self._clone_hint_value(example)

    @staticmethod
    def _clone_hint_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_copy(deep=True)
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    def _build_override_context(
        self,
        model_type: type[Any],
        field_name: str,
        summary: FieldSummary | None,
        values: Mapping[str, Any],
        entry: _PathEntry,
    ) -> FieldOverrideContext:
        alias = self._field_alias(model_type, field_name)
        path = f"{entry.full}.{field_name}"
        return FieldOverrideContext(
            model=model_type,
            field_name=field_name,
            alias=alias,
            summary=summary,
            faker=self.faker,
            random=self.random,
            values=values,
            path=path,
        )

    @staticmethod
    def _strategy_summary(strategy: StrategyResult) -> FieldSummary | None:
        if isinstance(strategy, Strategy):
            return strategy.summary
        return None

    def _detect_cycle_entry(self, model_type: type[Any]) -> _PathEntry | None:
        for entry in reversed(self._path_stack):
            if entry.model_type is model_type:
                return entry
        return None

    def _handle_cycle_resolution(
        self,
        model_type: type[Any],
        path: str,
        *,
        reason: str,
        ref_entry: _PathEntry | None,
    ) -> Any | None:
        policy = self._cycle_policy
        fallback: str | None = None
        ref_path = ref_entry.full if ref_entry is not None else None

        if policy == "null":
            value: Any | None = None
        elif policy == "stub":
            value = self._build_stub_instance(model_type)
        else:  # reuse
            value = self._clone_reusable_instance(model_type)
            if value is None:
                if ref_entry is not None:
                    value = self._build_partial_instance(model_type, ref_entry)
                    fallback = "partial"
                if value is None:
                    fallback = "stub"
                    value = self._build_stub_instance(model_type)

        self._cycle_events.append(
            CycleEvent(
                path=path,
                policy=policy,
                reason=reason,
                ref_path=ref_path,
                fallback=fallback,
            )
        )
        if value is None:
            self._note_generation_failure(
                "cycle_resolution_null",
                path=path,
                policy=policy,
                cycle_reason=reason,
                ref_path=ref_path,
            )
        return value

    def _clone_reusable_instance(self, model_type: type[Any]) -> BaseModel | None:
        bucket = self._reuse_pool.get(model_type)
        if not bucket:
            return None
        _, instance = bucket[0]
        try:
            return instance.model_copy(deep=True)
        except Exception:  # pragma: no cover - defensive fallback
            import copy

            return copy.deepcopy(instance)

    def _build_stub_instance(self, model_type: type[Any]) -> Any | None:
        if self._is_pydantic_model_type(model_type):
            construct = getattr(model_type, "model_construct", None)
            if callable(construct):
                try:
                    return construct()
                except Exception:
                    pass
            try:
                defaults = {name: None for name in self._model_field_names(model_type)}
                return model_type(**defaults)
            except Exception:
                return None
        if dataclasses.is_dataclass(model_type):
            values: dict[str, Any] = {}
            for field in dataclasses.fields(model_type):
                values[field.name] = None
            try:
                return model_type(**values)
            except Exception:  # pragma: no cover - defensive fallback
                return None
        if is_typeddict_type(model_type):
            try:
                defaults = {name: None for name in self._model_field_names(model_type)}
                return model_type(**defaults)
            except Exception:  # pragma: no cover - defensive fallback
                return None
        return None

    def _build_partial_instance(
        self,
        model_type: type[Any],
        entry: _PathEntry,
    ) -> Any | None:
        if not entry.partial_values:
            return None
        if self._is_pydantic_model_type(model_type):
            try:
                return model_type.model_construct(**entry.partial_values)
            except Exception:  # pragma: no cover - defensive fallback
                return None
        if dataclasses.is_dataclass(model_type):
            try:
                return model_type(**entry.partial_values)
            except Exception:  # pragma: no cover - defensive fallback
                return None
        if is_typeddict_type(model_type):
            try:
                return model_type(**entry.partial_values)
            except Exception:  # pragma: no cover - defensive fallback
                return None
        return None

    def _register_reusable_instance(
        self,
        model_type: type[Any],
        path: str,
        instance: Any,
    ) -> None:
        if not self._is_pydantic_model_type(model_type):
            return
        if not self._is_pydantic_instance(instance):
            return
        bucket = self._reuse_pool.setdefault(model_type, [])
        if bucket:
            return
        bucket.append((path, instance))

    def _evaluate_union(
        self,
        strategy: UnionStrategy,
        depth: int,
        model_type: type[Any],
        field_name: str,
        report_model: type[Any] | None,
    ) -> Any:
        choices = strategy.choices
        if not choices:
            return None

        selected = self.random.choice(choices) if strategy.policy == "random" else choices[0]
        return self._evaluate_single(selected, depth, model_type, field_name, report_model)

    def _evaluate_single(
        self,
        strategy: Strategy,
        depth: int,
        model_type: type[Any],
        field_name: str,
        report_model: type[Any] | None,
    ) -> Any:
        summary = strategy.summary
        if report_model is not None:
            self._constraint_reporter.record_field_attempt(report_model, field_name, summary)

        relation_value: Any = _RELATION_SKIP
        full_path, aliases = self._current_field_paths(field_name)
        if self._relation_manager is not None:
            keys = (full_path, *aliases)
            relation_value = self._relation_manager.resolve_value(
                model_keys=keys,
                field_name=field_name,
                generator=self,
                depth=depth,
            )

        if relation_value is not _RELATION_SKIP:
            value = relation_value
        elif self._should_return_none(strategy):
            value = None
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
                        current_path=full_path,
                    )
                elif summary.type in {"list", "set", "tuple", "mapping"}:
                    value = self._evaluate_collection(
                        model_type,
                        field_name,
                        strategy,
                        depth,
                        parent_path=full_path,
                    )
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
        parent_path: str,
    ) -> Any:
        summary = strategy.summary
        base_value = self._call_strategy_provider(model_type, field_name, strategy)

        item_strategy = strategy.collection_item_strategy
        if item_strategy is None:
            return base_value

        item_annotation = summary.item_annotation
        if item_annotation is None:
            return base_value

        desired_length = self._determine_collection_length(summary, strategy, base_value)

        if summary.type == "mapping":
            return self._build_mapping_collection(
                base_value,
                item_annotation,
                item_strategy,
                depth,
                model_type,
                field_name,
                desired_length,
            )

        values = self._build_sequence_collection(
            base_value,
            summary,
            item_strategy,
            desired_length,
            depth,
            model_type,
            field_name,
        )

        if summary.type == "list":
            return values
        if summary.type == "tuple":
            return tuple(values)
        if summary.type == "set":
            return set(values)
        return values

    def _build_mapping_collection(
        self,
        base_value: Any,
        annotation: Any,
        item_strategy: StrategyResult,
        depth: int,
        model_type: type[Any],
        field_name: str,
        length: int,
    ) -> dict[str, Any]:
        if length <= 0:
            return {}

        existing_keys: list[str] = []
        if isinstance(base_value, dict) and base_value:
            existing_keys = [str(key) for key in base_value]

        selected_keys: list[str] = existing_keys[:length]
        while len(selected_keys) < length:
            selected_keys.append(self.faker.pystr(min_chars=3, max_chars=6))

        result: dict[str, Any] = {}
        for index, key in enumerate(selected_keys):
            existing_value = None
            if isinstance(base_value, dict) and key in base_value:
                existing_value = base_value[key]
            if existing_value is not None:
                coerced = self._coerce_inline_value(existing_value, annotation)
            else:
                coerced = _HINT_UNSET
            if coerced is _HINT_UNSET:
                coerced = self._evaluate_collection_strategy(
                    item_strategy,
                    depth + 1,
                    model_type,
                    f"{field_name}[{index}]",
                )
            if coerced is not None:
                result[str(key)] = coerced
        return result

    def _build_sequence_collection(
        self,
        base_value: Any,
        summary: FieldSummary,
        item_strategy: StrategyResult,
        length: int,
        depth: int,
        model_type: type[Any],
        field_name: str,
    ) -> list[Any]:
        if length <= 0:
            return []

        existing: list[Any] = []
        if isinstance(base_value, (list, tuple, set)):
            existing = list(base_value)

        result: list[Any] = []
        annotation = summary.item_annotation
        for index in range(length):
            base_item = existing[index] if index < len(existing) else _HINT_UNSET
            if base_item is not _HINT_UNSET:
                coerced = self._coerce_inline_value(base_item, annotation)
            else:
                coerced = _HINT_UNSET
            if coerced is _HINT_UNSET:
                coerced = self._evaluate_collection_strategy(
                    item_strategy,
                    depth + 1,
                    model_type,
                    f"{field_name}[{index}]",
                )
            result.append(coerced)
        return result

    def _evaluate_collection_strategy(
        self,
        strategy: StrategyResult,
        depth: int,
        model_type: type[Any],
        field_name: str,
    ) -> Any:
        if isinstance(strategy, UnionStrategy):
            return self._evaluate_union(
                strategy,
                depth,
                model_type,
                field_name,
                report_model=None,
            )
        return self._evaluate_single(
            strategy,
            depth,
            model_type,
            field_name,
            report_model=None,
        )

    def _coerce_inline_value(self, value: Any, annotation: Any | None) -> Any:
        if annotation is None:
            return value
        try:
            adapter = TypeAdapter(annotation)
        except Exception:
            return _HINT_UNSET
        try:
            return adapter.validate_python(value)
        except ValidationError:
            return _HINT_UNSET

    def _consume_object(self) -> bool:
        if getattr(self, "_objects_remaining", 0) <= 0:
            return False
        self._objects_remaining -= 1
        return True

    def _get_model_strategies(self, model_type: type[Any]) -> dict[str, StrategyResult]:
        cached = self._strategy_cache.get(model_type)
        if cached is not None:
            return cached

        strategies = dict(self.builder.build_model_strategies(model_type))

        if self._field_override_set is not None:
            self._apply_strategy_overrides(model_type, strategies)

        self._strategy_cache[model_type] = strategies
        return strategies

    def _apply_strategy_overrides(
        self,
        model_type: type[Any],
        strategies: Mapping[str, StrategyResult],
    ) -> None:
        for field_name, strategy in strategies.items():
            override = self._field_override(model_type, field_name)
            if override is None or not override.affects_strategy:
                continue
            self._apply_override_to_strategy(
                model_type,
                field_name,
                strategy,
                override,
            )

    def _record_validator_failure(
        self,
        model_type: type[Any],
        values: Mapping[str, Any],
        *,
        message: str,
        errors: Iterable[Mapping[str, Any]],
    ) -> None:
        snapshot = {name: self._serialize_value(value) for name, value in values.items()}
        self._pending_validator_failure = {
            "model": self._describe_model(model_type),
            "message": message,
            "errors": list(errors),
            "values": snapshot,
        }

    def _note_generation_failure(
        self,
        reason: str,
        *,
        path: str | None = None,
        **context: Any,
    ) -> None:
        data: dict[str, Any] = {"reason": reason}
        if path:
            data["path"] = path
        elif self._path_stack:
            data["path"] = self._path_stack[-1].full
        for key, value in context.items():
            if value is not None:
                data[key] = value
        self._last_generation_failure = data

    @staticmethod
    def _is_pydantic_model_type(model_type: Any) -> bool:
        if not isinstance(model_type, type):
            return False
        try:
            if issubclass(model_type, BaseModel):
                return True
        except TypeError:
            pass
        return hasattr(model_type, "model_fields") or hasattr(model_type, "__fields__")

    @staticmethod
    def _is_pydantic_instance(value: Any) -> bool:
        if isinstance(value, BaseModel):
            return True
        return hasattr(value, "model_dump") or hasattr(value, "__fields__")

    @staticmethod
    def _model_field_names(model_type: type[Any]) -> list[str]:
        fields = getattr(model_type, "model_fields", None)
        if isinstance(fields, Mapping):
            return list(fields.keys())
        try:
            return list(schema_module.summarize_model_fields(model_type).keys())
        except TypeError:
            pass
        return []

    def _serialize_value(self, value: Any, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if depth > 2:
            return repr(value)
        if isinstance(value, BaseModel):
            try:
                return value.model_dump()
            except Exception:  # pragma: no cover - defensive
                return repr(value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            try:
                return dataclasses.asdict(value)
            except Exception:  # pragma: no cover - defensive
                return repr(value)
        if isinstance(value, dict):
            return {str(key): self._serialize_value(val, depth + 1) for key, val in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item, depth + 1) for item in value]
        if isinstance(value, tuple):
            return tuple(self._serialize_value(item, depth + 1) for item in value)
        if isinstance(value, set):
            return sorted(self._serialize_value(item, depth + 1) for item in value)
        return repr(value)

    def _should_return_none(self, strategy: Strategy) -> bool:
        if not strategy.summary.is_optional:
            return False
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

    def _determine_collection_length(
        self,
        summary: FieldSummary,
        strategy: Strategy,
        base_value: Any,
    ) -> int:
        config = strategy.collection_config or self.collection_config
        if config is None:
            length = self._collection_length_from_value(base_value)
            return max(1, length)
        length = sample_collection_length(config, summary.constraints, self.random)
        return max(0, length)

    @staticmethod
    def _is_model_like(annotation: Any) -> bool:
        if not isinstance(annotation, type):
            return False
        return (
            InstanceGenerator._is_pydantic_model_type(annotation)
            or is_dataclass(annotation)
            or is_typeddict_type(annotation)
        )

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
        summary = strategy.summary
        kwargs = {
            "summary": summary,
            "faker": faker,
            "random_generator": self.random,
            "time_anchor": self.config.time_anchor,
            "numpy_rng": numpy_rng,
            "path_config": self.path_config,
            "model_type": model_type,
        }
        if summary.type in {"list", "set", "tuple", "mapping"}:
            collection_config = strategy.collection_config or self.collection_config
            if collection_config is not None:
                kwargs.setdefault("collection_config", collection_config)
        kwargs.update(strategy.provider_kwargs)

        sig = inspect.signature(func)
        applicable = {name: value for name, value in kwargs.items() if name in sig.parameters}
        try:
            return func(**applicable)
        except Exception:
            return None


__all__ = ["InstanceGenerator", "GenerationConfig"]
