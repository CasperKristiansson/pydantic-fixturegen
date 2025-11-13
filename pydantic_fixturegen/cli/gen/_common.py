"""Shared helpers for generation CLI commands."""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import importlib
import importlib.util
import json
import sys
import typing
import uuid as _uuid
import warnings
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.config import FIELD_HINT_MODES
from pydantic_fixturegen.core.errors import PFGError
from pydantic_fixturegen.core.introspect import (
    IntrospectedModel,
    IntrospectionResult,
    discover,
)
from pydantic_fixturegen.logging import Logger
from pydantic_fixturegen.core.model_utils import (
    is_dataclass_type,
    is_pydantic_model,
    is_typeddict_type,
)

__all__ = [
    "JSON_ERRORS_OPTION",
    "NOW_OPTION",
    "LOCALE_OPTION",
    "LOCALE_MAP_OPTION",
    "OVERRIDES_OPTION",
    "RNG_MODE_OPTION",
    "FIELD_HINTS_OPTION",
    "COLLECTION_MIN_ITEMS_OPTION",
    "COLLECTION_MAX_ITEMS_OPTION",
    "COLLECTION_DISTRIBUTION_OPTION",
    "COLLECTION_MIN_ITEMS_OPTION",
    "COLLECTION_MAX_ITEMS_OPTION",
    "COLLECTION_DISTRIBUTION_OPTION",
    "clear_module_cache",
    "discover_models",
    "load_model_class",
    "render_cli_error",
    "split_patterns",
    "emit_constraint_summary",
    "parse_override_entries",
    "parse_locale_entries",
    "parse_relation_links",
    "evaluate_type_expression",
    "get_cached_module",
]


_module_cache: dict[str, ModuleType] = {}
_sys_path_injections: set[str] = set()
_CANONICAL_ATTR = "__pfg_canonical_name__"
_MODEL_CANONICAL_ATTR = "__pfg_canonical_module__"


JSON_ERRORS_OPTION = typer.Option(
    False,
    "--json-errors",
    help="Emit structured JSON errors to stdout.",
)

NOW_OPTION = typer.Option(
    None,
    "--now",
    help="Anchor timestamp (ISO 8601) used for temporal value generation.",
)

LOCALE_OPTION = typer.Option(
    None,
    "--locale",
    help="Override the default Faker locale for this run (e.g., sv_SE).",
)

LOCALE_MAP_OPTION = typer.Option(
    None,
    "--locale-map",
    "-L",
    help="Pattern=locale mapping (repeatable) applied to matching models or fields.",
)

RNG_MODE_OPTION = typer.Option(
    None,
    "--rng-mode",
    help="Random generator mode: 'portable' (default) or 'legacy'.",
)

OVERRIDES_OPTION = typer.Option(
    None,
    "--override",
    "-O",
    help=(
        "Per-field override entry (repeatable) formatted as Model.field={'value': 1} "
        "or Model.field={'factory': 'pkg.module:func'}."
    ),
)


def _validate_field_hint_mode(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered not in FIELD_HINT_MODES:
        raise typer.BadParameter(
            f"field hint mode must be one of {', '.join(sorted(FIELD_HINT_MODES))}."
        )
    return lowered


FIELD_HINTS_OPTION = typer.Option(
    None,
    "--field-hints",
    callback=_validate_field_hint_mode,
    help=(
        "Prefer field hints when available: none, defaults, examples, defaults-then-examples, "
        "examples-then-defaults."
    ),
)


def _validate_collection_distribution(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    valid = {"uniform", "min-heavy", "max-heavy"}
    if lowered not in valid:
        raise typer.BadParameter(
            f"collection distribution must be one of {', '.join(sorted(valid))}."
        )
    return lowered


COLLECTION_MIN_ITEMS_OPTION = typer.Option(
    None,
    "--collection-min-items",
    min=0,
    help="Override minimum items for generated collections (lists/sets/tuples/mappings).",
)

COLLECTION_MAX_ITEMS_OPTION = typer.Option(
    None,
    "--collection-max-items",
    min=0,
    help="Override maximum items for generated collections (lists/sets/tuples/mappings).",
)

COLLECTION_DISTRIBUTION_OPTION = typer.Option(
    None,
    "--collection-distribution",
    callback=_validate_collection_distribution,
    help="Distribution for collection lengths: uniform, min-heavy, max-heavy.",
)


def clear_module_cache() -> None:
    """Clear cached module imports used during CLI execution."""

    _module_cache.clear()
    stale_modules = [
        name for name, module in list(sys.modules.items()) if getattr(module, _CANONICAL_ATTR, None)
    ]
    for name in stale_modules:
        sys.modules.pop(name, None)
    for entry in list(_sys_path_injections):
        with suppress(ValueError):
            sys.path.remove(entry)
    _sys_path_injections.clear()

    with suppress(ModuleNotFoundError):
        from sqlmodel import SQLModel

        metadata = getattr(SQLModel, "metadata", None)
        if metadata is not None:
            metadata.clear()
        registry = getattr(SQLModel, "_sa_registry", None)
        if registry is not None:
            registry._class_registry.clear()


def split_patterns(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_relation_links(values: Sequence[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not values:
        return mapping
    for raw_value in values:
        if not raw_value:
            continue
        for entry in split_patterns(raw_value):
            if "=" not in entry:
                raise typer.BadParameter(
                    "Relation links must be formatted as 'source_model.field=target_model.field'."
                )
            source, target = entry.split("=", 1)
            source_key = source.strip()
            target_key = target.strip()
            if not source_key or not target_key:
                raise typer.BadParameter(
                    "Relation links must include both source and target fields."
                )
            mapping[source_key] = target_key
    return mapping


def parse_override_entries(entries: Sequence[str] | None) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    if not entries:
        return overrides
    for raw_entry in entries:
        if not raw_entry:
            continue
        if "=" not in raw_entry:
            raise typer.BadParameter(
                "Override entries must be formatted as 'Model.field={\"value\": ...}'."
            )
        path, payload = raw_entry.split("=", 1)
        path = path.strip()
        payload = payload.strip()
        if "." not in path:
            raise typer.BadParameter(
                "Override paths must include the model and field name (Model.field)."
            )
        model_key, field_key = path.rsplit(".", 1)
        model_key = model_key.strip()
        field_key = field_key.strip()
        if not model_key or not field_key:
            raise typer.BadParameter("Override paths must include non-empty model and field names.")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Override payload for '{path}' must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise typer.BadParameter(
                f"Override payload for '{path}' must be a JSON object containing override options."
            )
        overrides.setdefault(model_key, {})[field_key] = data
    return overrides


def parse_locale_entries(entries: Sequence[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not entries:
        return mapping
    for raw_entry in entries:
        if not raw_entry:
            continue
        if "=" not in raw_entry:
            raise typer.BadParameter(
                "Locale map entries must be formatted as 'pattern=locale'."
            )
        pattern, locale = raw_entry.split("=", 1)
        pattern = pattern.strip()
        locale_value = locale.strip()
        if not pattern or not locale_value:
            raise typer.BadParameter(
                "Locale map entries require both a pattern and locale value."
            )
        mapping[pattern] = locale_value
    return mapping


def _package_hierarchy(module_path: Path) -> list[Path]:
    hierarchy: list[Path] = []
    current = module_path.parent.resolve()

    while True:
        init_file = current / "__init__.py"
        if not init_file.exists():
            break
        hierarchy.append(current)
        parent = current.parent.resolve()
        if parent == current:
            break
        current = parent

    hierarchy.reverse()
    return hierarchy


def _module_sys_path_entries(module_path: Path) -> list[str]:
    resolved_path = module_path.resolve()
    candidates: list[Path] = []
    packages = _package_hierarchy(resolved_path)

    if packages:
        root_parent = packages[0].parent.resolve()
        if root_parent != packages[0] and root_parent.is_dir():
            candidates.append(root_parent)

    parent_dir = resolved_path.parent
    if parent_dir.is_dir():
        candidates.append(parent_dir.resolve())

    ordered: list[str] = []
    seen: set[str] = set()
    for entry in candidates:
        entry_str = str(entry)
        if entry_str in seen:
            continue
        ordered.append(entry_str)
        seen.add(entry_str)
    return ordered


DiscoveryMethod = Literal["ast", "import", "hybrid"]


def discover_models(
    path: Path,
    *,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    method: DiscoveryMethod = "import",
    timeout: float = 5.0,
    memory_limit_mb: int = 256,
) -> IntrospectionResult:
    return discover(
        [path],
        method=method,
        include=list(include or ()),
        exclude=list(exclude or ()),
        public_only=False,
        safe_import_timeout=timeout,
        safe_import_memory_limit_mb=memory_limit_mb,
    )


def load_model_class(model_info: IntrospectedModel) -> type[Any]:
    module = _load_module(model_info.module, Path(model_info.locator))
    attr = getattr(module, model_info.name, None)
    if (
        isinstance(attr, type)
        and not is_pydantic_model(attr)
        and getattr(module, "__pfg_schema_fallback__", False)
    ):
        attr = _promote_to_base_model(attr)
        setattr(module, model_info.name, attr)
    if not isinstance(attr, type):
        raise RuntimeError(
            f"Attribute {model_info.name!r} in module "
            f"{module.__name__} is not a supported model class."
        )
    if not (
        is_pydantic_model(attr)
        or is_dataclass_type(attr)
        or is_typeddict_type(attr)
    ):
        raise RuntimeError(
            f"Attribute {model_info.name!r} in module {module.__name__} is not a "
            "Pydantic model, dataclass, or TypedDict."
        )
    rebuild = getattr(attr, "model_rebuild", None)
    if callable(rebuild):  # pragma: no branch - harmless when absent
        namespace = getattr(module, "__dict__", {})
        rebuild(force=True, _types_namespace=namespace)
    return attr


def render_cli_error(error: PFGError, *, json_errors: bool, exit_app: bool = True) -> None:
    if json_errors:
        payload = {"error": error.to_payload()}
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.secho(f"{error.kind}: {error}", err=True, fg=typer.colors.RED)
        if error.details:
            try:
                detail_text = json.dumps(error.details, indent=2, default=str)
            except Exception:  # pragma: no cover - defensive
                detail_text = str(error.details)
            typer.secho("details:", err=True, fg=typer.colors.YELLOW)
            typer.echo(detail_text, err=True)
        if error.hint:
            typer.secho(f"hint: {error.hint}", err=True, fg=typer.colors.YELLOW)
    if exit_app:
        raise typer.Exit(code=int(error.code))


def emit_constraint_summary(
    report: Mapping[str, Any] | None,
    *,
    logger: Logger,
    json_mode: bool,
    heading: str | None = None,
) -> None:
    if not report:
        return

    models = report.get("models")
    if not models:
        return

    has_failures = any(
        field.get("failures") for model_entry in models for field in model_entry.get("fields", [])
    )

    event_payload = {"report": report, "heading": heading}

    if has_failures:
        logger.warn(
            "Constraint violations detected.",
            event="constraint_report",
            **event_payload,
        )
    else:
        logger.debug(
            "Constraint report recorded.",
            event="constraint_report",
            **event_payload,
        )

    if not has_failures or json_mode:
        return

    title = heading or "Constraint report"
    typer.secho(title + ":", fg=typer.colors.CYAN)

    for model_entry in models:
        fields = [field for field in model_entry.get("fields", []) if field.get("failures")]
        if not fields:
            continue

        typer.secho(
            (
                f"  {model_entry['model']} "
                f"(attempts={model_entry['attempts']}, successes={model_entry['successes']})"
            ),
            fg=typer.colors.CYAN,
        )
        for field_entry in fields:
            typer.secho(
                (
                    f"    {field_entry['name']} "
                    f"(attempts={field_entry['attempts']}, successes={field_entry['successes']})"
                ),
                fg=typer.colors.YELLOW,
            )
            for failure in field_entry.get("failures", []):
                location = failure.get("location") or [field_entry["name"]]
                location_display = ".".join(str(part) for part in location)
                typer.secho(
                    f"      ✖ {location_display}: {failure.get('message', '')}",
                    fg=typer.colors.RED,
                )
                if failure.get("value") is not None:
                    typer.echo(f"        value={failure['value']}")
                hint = failure.get("hint")
                if hint:
                    typer.secho(f"        hint: {hint}", fg=typer.colors.MAGENTA)


def _promote_to_base_model(model_cls: type[Any]) -> type[BaseModel]:
    annotations = dict(getattr(model_cls, "__annotations__", {}))
    namespace: dict[str, Any] = {"__module__": model_cls.__module__, "__annotations__": annotations}
    for key, value in vars(model_cls).items():
        if key.startswith("__") and key not in {"__annotations__", "__doc__"}:
            continue
        namespace[key] = value
    return type(model_cls.__name__, (BaseModel,), namespace)


def _load_module(module_name: str, locator: Path) -> ModuleType:
    module = _module_cache.get(module_name)
    if module is not None:
        return module

    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = getattr(existing, "__file__", None)
        if existing_path and Path(existing_path).resolve() == locator.resolve():
            _module_cache[module_name] = existing
            return existing

    return _import_module_by_path(module_name, locator)


def _import_module_by_path(module_name: str, path: Path) -> ModuleType:
    if not path.exists():
        raise RuntimeError(f"Could not locate module source at {path}.")

    sys_path_entries = _module_sys_path_entries(path)
    for entry in reversed(sys_path_entries):
        if entry not in sys.path:
            sys.path.insert(0, entry)
            _sys_path_injections.add(entry)

    unique_name = module_name
    if module_name in sys.modules:
        unique_name = f"{module_name}_pfg_{len(_module_cache)}"

    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}.")

    module = importlib.util.module_from_spec(spec)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=(
                    r"The `__get_pydantic_core_schema__` method of the `BaseModel` "
                    r"class is deprecated\."
                ),
                category=DeprecationWarning,
            )
            spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - surface to caller
        raise RuntimeError(f"Error importing module {path}: {exc}") from exc

    _annotate_canonical_names(module, module_name)
    _module_cache[module_name] = module
    return module


def get_cached_module(module_name: str) -> ModuleType | None:
    return _module_cache.get(module_name)


def _annotate_canonical_names(module: ModuleType, canonical_name: str) -> None:
    setattr(module, _CANONICAL_ATTR, canonical_name)
    module_name = getattr(module, "__name__", None)
    if not module_name:
        return

    for value in module.__dict__.values():
        owner = getattr(value, "__module__", None)
        if owner != module_name:
            continue
        try:
            setattr(value, _MODEL_CANONICAL_ATTR, canonical_name)
        except Exception:  # pragma: no cover - attribute may be read-only
            continue


def evaluate_type_expression(expression: str, *, module_path: Path | None = None) -> Any:
    """Evaluate a Python type expression in a constrained namespace."""

    module = None
    if module_path is not None:
        module = _import_module_by_path(module_path.stem, module_path)
    namespace = _build_type_namespace(module)
    try:
        return eval(expression, {"__builtins__": {}}, namespace)
    except NameError as exc:
        raise ValueError(f"Unknown name in type expression: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Invalid type expression: {exc}") from exc


def _build_type_namespace(extra_module: ModuleType | None) -> dict[str, Any]:
    ns: dict[str, Any] = {
        "typing": typing,
        "Path": Path,
        "datetime": _dt,
        "date": _dt.date,
        "time": _dt.time,
        "timedelta": _dt.timedelta,
        "timezone": _dt.timezone,
        "Decimal": _decimal.Decimal,
        "uuid": _uuid,
        "UUID": _uuid.UUID,
        "BaseModel": BaseModel,
    }

    for builtin in (list, dict, set, tuple, frozenset, int, float, bool, str):
        ns[builtin.__name__] = builtin

    ns.setdefault("Literal", typing.Literal)
    ns.setdefault("Annotated", typing.Annotated)
    ns.setdefault("Union", typing.Union)
    ns.setdefault("Any", typing.Any)
    ns.setdefault("Optional", typing.Optional)

    pydantic_module = _maybe_import("pydantic")
    if pydantic_module is not None:
        ns.setdefault("pydantic", pydantic_module)
        for attr in ("EmailStr", "AnyUrl", "AnyHttpUrl", "TypeAdapter"):
            if hasattr(pydantic_module, attr):
                ns.setdefault(attr, getattr(pydantic_module, attr))

    extra_pkg = _maybe_import("pydantic_extra_types")
    if extra_pkg is not None:
        ns.setdefault("pydantic_extra_types", extra_pkg)

    if extra_module is not None:
        ns.setdefault(extra_module.__name__, extra_module)
        for name, value in vars(extra_module).items():
            if name.startswith("_"):
                continue
            ns.setdefault(name, value)

    return ns


def _maybe_import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None
