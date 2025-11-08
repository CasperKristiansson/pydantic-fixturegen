"""Shared runtime helpers for the Python API and CLI commands."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, TypeAdapter, ValidationError, create_model

from pydantic_fixturegen.core.config import AppConfig, load_config
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, MappingError, PFGError
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.introspect import IntrospectedModel
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.core.seed_freeze import (
    FreezeStatus,
    SeedFreezeFile,
    compute_model_digest,
    derive_default_model_seed,
    model_identifier,
    resolve_freeze_path,
)
from pydantic_fixturegen.emitters.json_out import emit_json_samples
from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from ..logging import Logger
from .models import (
    ConfigSnapshot,
    FixturesGenerationResult,
    JsonGenerationResult,
    SchemaGenerationResult,
)


def _snapshot_config(app_config: AppConfig) -> ConfigSnapshot:
    return ConfigSnapshot(
        seed=app_config.seed,
        include=tuple(app_config.include),
        exclude=tuple(app_config.exclude),
        time_anchor=app_config.now,
    )


def _config_details(snapshot: ConfigSnapshot) -> dict[str, Any]:
    return {
        "seed": snapshot.seed,
        "include": list(snapshot.include),
        "exclude": list(snapshot.exclude),
        "time_anchor": snapshot.time_anchor.isoformat() if snapshot.time_anchor else None,
    }


def _split_patterns(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _build_error_details(
    *,
    config_snapshot: ConfigSnapshot,
    warnings: Sequence[str],
    base_output: Path,
    constraint_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "config": _config_details(config_snapshot),
        "warnings": list(warnings),
        "base_output": str(base_output),
    }
    if constraint_summary:
        details["constraint_summary"] = constraint_summary
    return details


def _attach_error_details(exc: PFGError, details: Mapping[str, Any]) -> None:
    for key, value in details.items():
        exc.details.setdefault(key, value)


def _summarize_constraint_report(reporter: Any) -> Mapping[str, Any] | None:
    if reporter is None:
        return None
    summary = reporter.summary()
    if isinstance(summary, dict):
        return summary
    return None


def _resolve_patterns(patterns: Sequence[str] | None) -> Sequence[str] | None:
    if patterns is None:
        return None
    resolved: list[str] = []
    for pattern in patterns:
        resolved.extend(_split_patterns(pattern))
    return resolved


def _collect_warnings(messages: Iterable[str]) -> tuple[str, ...]:
    return tuple(message.strip() for message in messages if message.strip())


def _build_relation_model_map(
    model_classes: Sequence[type[BaseModel]],
) -> dict[str, type[BaseModel]]:
    mapping: dict[str, type[BaseModel]] = {}
    for cls in model_classes:
        full = InstanceGenerator._describe_model(cls)
        mapping[full] = cls
        mapping.setdefault(cls.__qualname__, cls)
        mapping.setdefault(cls.__name__, cls)
    return mapping


def _build_instance_generator(
    app_config: AppConfig,
    *,
    seed_override: int | None = None,
    relation_models: Mapping[str, type[BaseModel]] | None = None,
) -> InstanceGenerator:
    if seed_override is not None:
        seed_value: int | None = seed_override
    else:
        seed_value = None
        if app_config.seed is not None:
            seed_value = SeedManager(seed=app_config.seed).normalized_seed

    p_none = app_config.p_none if app_config.p_none is not None else 0.0
    gen_config = GenerationConfig(
        seed=seed_value,
        enum_policy=app_config.enum_policy,
        union_policy=app_config.union_policy,
        default_p_none=p_none,
        optional_p_none=p_none,
        time_anchor=app_config.now,
        field_policies=app_config.field_policies,
        locale=app_config.locale,
        locale_policies=app_config.locale_policies,
        arrays=app_config.arrays,
        identifiers=app_config.identifiers,
        numbers=app_config.numbers,
        paths=app_config.paths,
        respect_validators=app_config.respect_validators,
        validator_max_retries=app_config.validator_max_retries,
        relations=app_config.relations,
        relation_models=relation_models or {},
    )
    return InstanceGenerator(config=gen_config)


def generate_json_artifacts(
    *,
    target: str | Path | None,
    output_template: OutputTemplate,
    count: int,
    jsonl: bool,
    indent: int | None,
    use_orjson: bool | None,
    shard_size: int | None,
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
    seed: int | None,
    now: str | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None = None,
    respect_validators: bool | None = None,
    validator_max_retries: int | None = None,
    relations: Mapping[str, str] | None = None,
    with_related: Sequence[str] | None = None,
    type_annotation: Any | None = None,
    type_label: str | None = None,
    logger: Logger | None = None,
) -> JsonGenerationResult:
    from ..cli.gen import _common as cli_common

    logger = logger or get_logger()

    path: Path | None = None
    if target is not None:
        path = Path(target)
        if not path.exists():
            raise DiscoveryError(
                f"Target path '{target}' does not exist.",
                details={"path": target},
            )
        if not path.is_file():
            raise DiscoveryError(
                "Target must be a Python module file.",
                details={"path": target},
            )
    elif type_annotation is None:
        raise DiscoveryError("Target path must be provided when no --type is specified.")

    if type_annotation is not None:
        if freeze_seeds:
            raise DiscoveryError("Seed freezing is not supported with --type targets.")
        if relations:
            raise DiscoveryError("Relation links cannot be combined with --type targets.")
        if with_related:
            raise DiscoveryError("Related model generation is unavailable for --type targets.")

    clear_include = _resolve_patterns(include)
    clear_exclude = _resolve_patterns(exclude)
    related_identifiers: list[str] = []
    related_include_patterns: list[str] = []
    if with_related:
        for identifier in with_related:
            related_identifiers.append(identifier)
            if any(marker in identifier for marker in ("*", "?", ".")):
                related_include_patterns.append(identifier)
            else:
                related_include_patterns.append(f"*.{identifier}")

    cli_common.clear_module_cache()
    load_entrypoint_plugins()

    freeze_manager: SeedFreezeFile | None = None
    if freeze_seeds:
        freeze_path = resolve_freeze_path(freeze_seeds_file, root=Path.cwd())
        freeze_manager = SeedFreezeFile.load(freeze_path)
        for message in freeze_manager.messages:
            logger.warn(
                "Seed freeze file ignored",
                event="seed_freeze_invalid",
                path=str(freeze_manager.path),
                reason=message,
            )

    cli_overrides: dict[str, Any] = {}
    if preset is not None:
        cli_overrides["preset"] = preset
    if profile is not None:
        cli_overrides["profile"] = profile
    if seed is not None:
        cli_overrides["seed"] = seed
    if now is not None:
        cli_overrides["now"] = now
    if respect_validators is not None:
        cli_overrides["respect_validators"] = respect_validators
    if validator_max_retries is not None:
        cli_overrides["validator_max_retries"] = validator_max_retries
    json_overrides: dict[str, Any] = {}
    if indent is not None:
        json_overrides["indent"] = indent
    if use_orjson is not None:
        json_overrides["orjson"] = use_orjson
    if json_overrides:
        cli_overrides["json"] = json_overrides
    include_values: list[str] | None = None
    if clear_include is not None:
        include_values = list(clear_include)
        if related_include_patterns:
            include_values.extend(related_include_patterns)
    elif related_include_patterns:
        include_values = ["*"]
        include_values.extend(related_include_patterns)
    if include_values:
        cli_overrides["include"] = include_values
    if clear_exclude:
        cli_overrides["exclude"] = list(clear_exclude)
    if relations:
        cli_overrides["relations"] = dict(relations)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)
    config_snapshot = _snapshot_config(app_config)

    if type_annotation is not None:
        return _generate_type_adapter_json(
            annotation=type_annotation,
            label=type_label,
            app_config=app_config,
            config_snapshot=config_snapshot,
            output_template=output_template,
            count=count,
            jsonl=jsonl,
            indent=indent,
            use_orjson=use_orjson,
            shard_size=shard_size,
        )

    assert path is not None
    discovery = cli_common.discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    warnings = _collect_warnings(discovery.warnings)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    related_infos: list[IntrospectedModel] = []
    related_set: set[str] = set()
    if related_identifiers:
        for identifier in related_identifiers:
            match = next(
                (
                    model
                    for model in discovery.models
                    if model.qualname == identifier or model.name == identifier
                ),
                None,
            )
            if match is None:
                raise DiscoveryError(f"Related model '{identifier}' not found.")
            if match.qualname in related_set:
                continue
            related_infos.append(match)
            related_set.add(match.qualname)

    remaining_models = [model for model in discovery.models if model.qualname not in related_set]

    if not remaining_models:
        raise DiscoveryError("No primary model discovered.")
    if len(remaining_models) > 1:
        names = ", ".join(model.qualname for model in remaining_models)
        raise DiscoveryError(
            f"Multiple models discovered ({names}). Use include/exclude to narrow selection.",
            details={"models": names},
        )

    target_model = remaining_models[0]

    try:
        model_class_lookup = {
            model.qualname: cli_common.load_model_class(model) for model in discovery.models
        }
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise DiscoveryError(str(exc)) from exc

    model_cls = model_class_lookup[target_model.qualname]
    related_model_classes = [model_class_lookup[info.qualname] for info in related_infos]

    model_id = model_identifier(model_cls)
    model_digest = compute_model_digest(model_cls)

    if freeze_manager is not None:
        default_seed = derive_default_model_seed(app_config.seed, model_id)
        selected_seed: int | None = default_seed
        stored_seed, status = freeze_manager.resolve_seed(model_id, model_digest=model_digest)
        if status is FreezeStatus.VALID and stored_seed is not None:
            selected_seed = stored_seed
        else:
            event = "seed_freeze_missing" if status is FreezeStatus.MISSING else "seed_freeze_stale"
            logger.warn(
                "Seed freeze entry unavailable; deriving new seed",
                event=event,
                model=model_id,
                path=str(freeze_manager.path),
            )
            selected_seed = default_seed
    else:
        selected_seed = None

    relation_model_map = _build_relation_model_map(list(model_class_lookup.values()))

    generator = _build_instance_generator(
        app_config,
        seed_override=selected_seed,
        relation_models=relation_model_map,
    )

    related_class_tuple = tuple(related_model_classes)

    def sample_factory() -> BaseModel | dict[str, Any]:
        related_instances: list[tuple[type[BaseModel], BaseModel]] = []
        for related_cls in related_class_tuple:
            related_instance = generator.generate_one(related_cls)
            if related_instance is None:
                raise MappingError(
                    f"Failed to generate instance for {related_cls.__qualname__}.",
                    details={"model": related_cls.__qualname__},
                )
            related_instances.append((related_cls, related_instance))

        instance = generator.generate_one(model_cls)
        if instance is None:
            details: dict[str, Any] = {"model": target_model.qualname}
            failure = getattr(generator, "validator_failure_details", None)
            if failure:
                details["validator_failure"] = failure
            summary_snapshot = _summarize_constraint_report(generator.constraint_report)
            if summary_snapshot:
                details["constraint_summary"] = summary_snapshot
            raise MappingError(
                f"Failed to generate instance for {target_model.qualname}.",
                details=details,
            )
        if related_instances:
            bundle: dict[str, Any] = {model_cls.__name__: instance.model_dump()}
            for related_cls, related_instance in related_instances:
                bundle[related_cls.__name__] = related_instance.model_dump()
            return bundle
        return instance

    indent_value = indent if indent is not None else app_config.json.indent
    use_orjson_value = use_orjson if use_orjson is not None else app_config.json.orjson

    timestamp = _dt.datetime.now(_dt.timezone.utc)
    template_context = OutputTemplateContext(
        model=model_cls.__name__,
        timestamp=timestamp,
    )
    base_output = output_template.render(
        context=template_context,
        case_index=1 if output_template.uses_case_index() else None,
    )

    context = EmitterContext(
        models=(model_cls,),
        output=base_output,
        parameters={
            "count": count,
            "jsonl": jsonl,
            "indent": indent_value,
            "shard_size": shard_size,
            "use_orjson": use_orjson_value,
            "path_template": output_template.raw,
        },
    )

    if emit_artifact("json", context):
        return JsonGenerationResult(
            paths=(),
            base_output=base_output,
            model=model_cls,
            config=config_snapshot,
            constraint_summary=None,
            warnings=warnings,
            delegated=True,
        )

    reporter = getattr(generator, "constraint_report", None)
    try:
        paths = emit_json_samples(
            sample_factory,
            output_path=output_template.raw,
            count=count,
            jsonl=jsonl,
            indent=indent_value,
            shard_size=shard_size,
            use_orjson=use_orjson_value,
            ensure_ascii=False,
            template=output_template,
            template_context=template_context,
        )
    except RuntimeError as exc:
        constraint_summary = _summarize_constraint_report(reporter)
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=base_output,
            constraint_summary=constraint_summary,
        )
        raise EmitError(str(exc), details=details) from exc
    except PFGError as exc:
        constraint_summary = _summarize_constraint_report(reporter)
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=base_output,
            constraint_summary=constraint_summary,
        )
        _attach_error_details(exc, details)
        raise

    if freeze_manager is not None:
        assert selected_seed is not None
        freeze_manager.record_seed(model_id, selected_seed, model_digest=model_digest)
        freeze_manager.save()

    constraint_summary = _summarize_constraint_report(reporter)

    return JsonGenerationResult(
        paths=tuple(paths),
        base_output=base_output,
        model=model_cls,
        config=config_snapshot,
        constraint_summary=constraint_summary,
        warnings=warnings,
        delegated=False,
    )


def _generate_type_adapter_json(
    *,
    annotation: Any,
    label: str | None,
    app_config: AppConfig,
    config_snapshot: ConfigSnapshot,
    output_template: OutputTemplate,
    count: int,
    jsonl: bool,
    indent: int | None,
    use_orjson: bool | None,
    shard_size: int | None,
) -> JsonGenerationResult:
    generator = _build_instance_generator(app_config)
    adapter = TypeAdapter(annotation)
    model_name = f"_PFGTypeAdapter_{abs(hash(label or 'TypeAdapter'))}"
    adapter_model = create_model(
        model_name,
        __base__=BaseModel,
        value=(annotation, ...),
    )

    reporter = getattr(generator, "constraint_report", None)
    warnings: tuple[str, ...] = ()
    indent_value = indent if indent is not None else app_config.json.indent
    use_orjson_value = use_orjson if use_orjson is not None else app_config.json.orjson
    timestamp = _dt.datetime.now(_dt.timezone.utc)
    display_label = label or "TypeAdapter"
    safe_label = _sanitize_identifier(display_label)
    template_context = OutputTemplateContext(model=safe_label, timestamp=timestamp)
    base_output = output_template.render(
        context=template_context,
        case_index=1 if output_template.uses_case_index() else None,
    )

    context = EmitterContext(
        models=(),
        output=base_output,
        parameters={
            "count": count,
            "jsonl": jsonl,
            "indent": indent_value,
            "shard_size": shard_size,
            "use_orjson": use_orjson_value,
            "path_template": output_template.raw,
        },
    )

    if emit_artifact("json", context):
        return JsonGenerationResult(
            paths=(),
            base_output=base_output,
            model=None,
            config=config_snapshot,
            constraint_summary=None,
            warnings=warnings,
            delegated=True,
            type_annotation=annotation,
            type_label=display_label,
        )

    def sample_factory() -> Any:
        instance = generator.generate_one(adapter_model)
        if instance is None:
            details: dict[str, Any] = {"type_adapter": safe_label}
            failure = getattr(generator, "validator_failure_details", None)
            if failure:
                details["validator_failure"] = failure
            summary_snapshot = _summarize_constraint_report(generator.constraint_report)
            if summary_snapshot:
                details["constraint_summary"] = summary_snapshot
            raise MappingError(
                f"Failed to generate value for {safe_label}.",
                details=details,
            )
        raw_value = getattr(instance, "value", None)
        try:
            validated = adapter.validate_python(raw_value)
        except ValidationError as exc:
            raise MappingError(
                f"TypeAdapter validation failed for {safe_label}.",
                details={"error": str(exc)},
            ) from exc
        return adapter.dump_python(validated)

    try:
        paths = emit_json_samples(
            sample_factory,
            output_path=output_template.raw,
            count=count,
            jsonl=jsonl,
            indent=indent_value,
            shard_size=shard_size,
            use_orjson=use_orjson_value,
            ensure_ascii=False,
            template=output_template,
            template_context=template_context,
        )
    except RuntimeError as exc:
        constraint_summary = _summarize_constraint_report(reporter)
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=base_output,
            constraint_summary=constraint_summary,
        )
        raise EmitError(str(exc), details=details) from exc
    except PFGError as exc:
        constraint_summary = _summarize_constraint_report(reporter)
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=base_output,
            constraint_summary=constraint_summary,
        )
        _attach_error_details(exc, details)
        raise

    constraint_summary = _summarize_constraint_report(reporter)

    return JsonGenerationResult(
        paths=tuple(paths),
        base_output=base_output,
        model=None,
        config=config_snapshot,
        constraint_summary=constraint_summary,
        warnings=warnings,
        delegated=False,
        type_annotation=annotation,
        type_label=display_label,
    )


def _sanitize_identifier(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value)
    cleaned = cleaned.strip("_")
    return cleaned or "TypeAdapter"


def generate_fixtures_artifacts(
    *,
    target: str | Path,
    output_template: OutputTemplate,
    style: str | None,
    scope: str | None,
    cases: int,
    return_type: str | None,
    seed: int | None,
    now: str | None,
    p_none: float | None,
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
    freeze_seeds: bool,
    freeze_seeds_file: Path | None,
    preset: str | None,
    profile: str | None = None,
    respect_validators: bool | None = None,
    validator_max_retries: int | None = None,
    relations: Mapping[str, str] | None = None,
    with_related: Sequence[str] | None = None,
    logger: Logger | None = None,
) -> FixturesGenerationResult:
    from ..cli.gen import _common as cli_common

    logger = logger or get_logger()

    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    clear_include = _resolve_patterns(include)
    clear_exclude = _resolve_patterns(exclude)
    related_include_patterns: list[str] = []
    if with_related:
        for identifier in with_related:
            if any(marker in identifier for marker in ("*", "?", ".")):
                related_include_patterns.append(identifier)
            else:
                related_include_patterns.append(f"*.{identifier}")

    cli_common.clear_module_cache()
    load_entrypoint_plugins()

    freeze_manager: SeedFreezeFile | None = None
    if freeze_seeds:
        freeze_path = resolve_freeze_path(freeze_seeds_file, root=Path.cwd())
        freeze_manager = SeedFreezeFile.load(freeze_path)
        for message in freeze_manager.messages:
            logger.warn(
                "Seed freeze file ignored",
                event="seed_freeze_invalid",
                path=str(freeze_path),
                reason=message,
            )

    cli_overrides: dict[str, Any] = {}
    if preset is not None:
        cli_overrides["preset"] = preset
    if profile is not None:
        cli_overrides["profile"] = profile
    if seed is not None:
        cli_overrides["seed"] = seed
    if now is not None:
        cli_overrides["now"] = now
    if p_none is not None:
        cli_overrides["p_none"] = p_none
    if respect_validators is not None:
        cli_overrides["respect_validators"] = respect_validators
    if validator_max_retries is not None:
        cli_overrides["validator_max_retries"] = validator_max_retries
    emitter_overrides: dict[str, Any] = {}
    if style is not None:
        emitter_overrides["style"] = style
    if scope is not None:
        emitter_overrides["scope"] = scope
    if emitter_overrides:
        cli_overrides["emitters"] = {"pytest": emitter_overrides}
    include_values: list[str] | None = None
    if clear_include is not None:
        include_values = list(clear_include)
        if related_include_patterns:
            include_values.extend(related_include_patterns)
    elif related_include_patterns:
        include_values = ["*"]
        include_values.extend(related_include_patterns)
    if include_values:
        cli_overrides["include"] = include_values
    if clear_exclude:
        cli_overrides["exclude"] = list(clear_exclude)
    if relations:
        cli_overrides["relations"] = dict(relations)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)
    config_snapshot = _snapshot_config(app_config)

    discovery = cli_common.discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    warnings = _collect_warnings(discovery.warnings)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    available_names = {model.qualname for model in discovery.models}
    available_names.update(model.name for model in discovery.models)
    if with_related:
        for identifier in with_related:
            if identifier not in available_names:
                raise DiscoveryError(f"Related model '{identifier}' not found.")

    try:
        model_classes = [cli_common.load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise DiscoveryError(str(exc)) from exc

    seed_value: int | None = None
    if app_config.seed is not None:
        seed_value = SeedManager(seed=app_config.seed).normalized_seed

    style_value = style or app_config.emitters.pytest.style
    scope_value = scope or app_config.emitters.pytest.scope
    return_type_value = return_type or "model"

    style_literal = cast(Literal["functions", "factory", "class"], style_value)
    return_type_literal = cast(Literal["model", "dict"], return_type_value)

    per_model_seeds: dict[str, int] = {}
    model_digests: dict[str, str | None] = {}

    for model_cls in model_classes:
        model_id = model_identifier(model_cls)
        digest = compute_model_digest(model_cls)
        model_digests[model_id] = digest

        if freeze_manager is not None:
            default_seed = derive_default_model_seed(app_config.seed, model_id)
            selected_seed = default_seed
            stored_seed, status = freeze_manager.resolve_seed(model_id, model_digest=digest)
            if status is FreezeStatus.VALID and stored_seed is not None:
                selected_seed = stored_seed
            else:
                event = (
                    "seed_freeze_missing" if status is FreezeStatus.MISSING else "seed_freeze_stale"
                )
                logger.warn(
                    "Seed freeze entry unavailable; deriving new seed",
                    event=event,
                    model=model_id,
                    path=str(freeze_manager.path),
                )
                selected_seed = default_seed
        else:
            selected_seed = derive_default_model_seed(app_config.seed, model_id)

        per_model_seeds[model_id] = selected_seed

    header_seed = seed_value if freeze_manager is None else None

    relation_model_map = _build_relation_model_map(model_classes)

    pytest_config = PytestEmitConfig(
        scope=scope_value,
        style=style_literal,
        return_type=return_type_literal,
        cases=cases,
        seed=header_seed,
        optional_p_none=app_config.p_none,
        per_model_seeds=per_model_seeds if freeze_manager is not None else None,
        time_anchor=app_config.now,
        field_policies=app_config.field_policies,
        locale=app_config.locale,
        locale_policies=app_config.locale_policies,
        arrays=app_config.arrays,
        identifiers=app_config.identifiers,
        paths=app_config.paths,
        numbers=app_config.numbers,
        respect_validators=app_config.respect_validators,
        validator_max_retries=app_config.validator_max_retries,
        relations=app_config.relations,
        relation_models=relation_model_map,
    )

    timestamp = _dt.datetime.now(_dt.timezone.utc)
    template_context = OutputTemplateContext(
        model="combined" if len(model_classes) > 1 else model_classes[0].__name__,
        timestamp=timestamp,
    )
    resolved_output = output_template.render(
        context=template_context,
        case_index=1 if output_template.uses_case_index() else None,
    )

    context = EmitterContext(
        models=tuple(model_classes),
        output=resolved_output,
        parameters={
            "style": style_value,
            "scope": scope_value,
            "cases": cases,
            "return_type": return_type_value,
            "path_template": output_template.raw,
        },
    )

    if emit_artifact("fixtures", context):
        return FixturesGenerationResult(
            path=None,
            base_output=resolved_output,
            models=tuple(model_classes),
            config=config_snapshot,
            metadata=None,
            warnings=warnings,
            constraint_summary=None,
            skipped=False,
            delegated=True,
            style=style_value,
            scope=scope_value,
            return_type=return_type_value,
            cases=cases,
        )

    try:
        result = emit_pytest_fixtures(
            model_classes,
            output_path=output_template.raw,
            config=pytest_config,
            template=output_template,
            template_context=template_context,
        )
    except PFGError as exc:
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=resolved_output,
            constraint_summary=None,
        )
        _attach_error_details(exc, details)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=resolved_output,
            constraint_summary=None,
        )
        raise EmitError(str(exc), details=details) from exc

    constraint_summary = None
    if result.metadata and "constraints" in result.metadata:
        summary_value = result.metadata.get("constraints")
        if isinstance(summary_value, dict):
            constraint_summary = summary_value

    if freeze_manager is not None:
        for model_cls in model_classes:
            model_id = model_identifier(model_cls)
            freeze_manager.record_seed(
                model_id,
                per_model_seeds[model_id],
                model_digest=model_digests[model_id],
            )
        freeze_manager.save()

    return FixturesGenerationResult(
        path=result.path,
        base_output=resolved_output,
        models=tuple(model_classes),
        config=config_snapshot,
        metadata=result.metadata or {},
        warnings=warnings,
        constraint_summary=constraint_summary,
        skipped=result.skipped,
        delegated=False,
        style=style_literal,
        scope=scope_value,
        return_type=return_type_literal,
        cases=cases,
    )


def generate_schema_artifacts(
    *,
    target: str | Path,
    output_template: OutputTemplate,
    indent: int | None,
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
    profile: str | None = None,
    logger: Logger | None = None,
) -> SchemaGenerationResult:
    logger = logger or get_logger()
    from ..cli.gen import _common as cli_common

    path = Path(target)
    if not path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    clear_include = _resolve_patterns(include)
    clear_exclude = _resolve_patterns(exclude)

    cli_common.clear_module_cache()
    load_entrypoint_plugins()

    cli_overrides: dict[str, Any] = {}
    if indent is not None:
        cli_overrides.setdefault("json", {})["indent"] = indent
    if profile is not None:
        cli_overrides["profile"] = profile
    if clear_include:
        cli_overrides["include"] = list(clear_include)
    if clear_exclude:
        cli_overrides["exclude"] = list(clear_exclude)

    app_config = load_config(root=Path.cwd(), cli=cli_overrides if cli_overrides else None)
    config_snapshot = _snapshot_config(app_config)

    discovery = cli_common.discover_models(
        path,
        include=app_config.include,
        exclude=app_config.exclude,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    warnings = _collect_warnings(discovery.warnings)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    try:
        model_classes = [cli_common.load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:  # pragma: no cover - defensive
        raise DiscoveryError(str(exc)) from exc

    indent_value = indent if indent is not None else app_config.json.indent

    if len(model_classes) > 1 and "model" in output_template.fields:
        names = ", ".join(cls.__name__ for cls in model_classes)
        raise EmitError(
            "Template variable '{model}' requires a single model selection.",
            details={
                "config": _config_details(config_snapshot),
                "warnings": list(warnings),
                "models": names,
            },
        )

    timestamp = _dt.datetime.now(_dt.timezone.utc)
    template_context = OutputTemplateContext(
        model="combined" if len(model_classes) > 1 else model_classes[0].__name__,
        timestamp=timestamp,
    )
    resolved_output = output_template.render(
        context=template_context,
        case_index=1 if output_template.uses_case_index() else None,
    )

    context = EmitterContext(
        models=tuple(model_classes),
        output=resolved_output,
        parameters={"indent": indent_value, "path_template": output_template.raw},
    )

    if emit_artifact("schema", context):
        return SchemaGenerationResult(
            path=None,
            base_output=resolved_output,
            models=tuple(model_classes),
            config=config_snapshot,
            warnings=warnings,
            delegated=True,
        )

    try:
        if len(model_classes) == 1:
            emitted_path = emit_model_schema(
                model_classes[0],
                output_path=output_template.raw,
                indent=indent_value,
                ensure_ascii=False,
                template=output_template,
                template_context=template_context,
            )
        else:
            emitted_path = emit_models_schema(
                model_classes,
                output_path=output_template.raw,
                indent=indent_value,
                ensure_ascii=False,
                template=output_template,
                template_context=template_context,
            )
    except Exception as exc:  # pragma: no cover - defensive
        details = _build_error_details(
            config_snapshot=config_snapshot,
            warnings=warnings,
            base_output=resolved_output,
            constraint_summary=None,
        )
        raise EmitError(str(exc), details=details) from exc

    return SchemaGenerationResult(
        path=emitted_path,
        base_output=resolved_output,
        models=tuple(model_classes),
        config=config_snapshot,
        warnings=warnings,
        delegated=False,
    )


__all__ = [
    "generate_json_artifacts",
    "generate_fixtures_artifacts",
    "generate_schema_artifacts",
]
