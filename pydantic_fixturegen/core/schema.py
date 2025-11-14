"""Utilities for extracting constraint metadata from Pydantic models."""

from __future__ import annotations

import dataclasses as dataclasses_module
import datetime
import decimal
import enum
import pathlib
import types
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin, get_type_hints

import annotated_types
import pydantic
from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typing_extensions import NotRequired, Required

from pydantic_fixturegen.core.extra_types import resolve_type_id
from pydantic_fixturegen.core.forward_refs import resolve_forward_ref
from pydantic_fixturegen.core.model_utils import is_dataclass_type, is_typeddict_type

_np: types.ModuleType | None
try:  # Optional dependency
    import numpy as _np
except ModuleNotFoundError:  # pragma: no cover - optional extra not installed
    _np = None


@dataclass(slots=True)
class FieldConstraints:
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None
    multiple_of: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    max_digits: int | None = None
    decimal_places: int | None = None

    def has_constraints(self) -> bool:
        return any(
            value is not None
            for value in (
                self.ge,
                self.le,
                self.gt,
                self.lt,
                self.multiple_of,
                self.min_length,
                self.max_length,
                self.pattern,
                self.max_digits,
                self.decimal_places,
            )
        )


@dataclass(slots=True)
class FieldSummary:
    type: str
    constraints: FieldConstraints
    format: str | None = None
    item_type: str | None = None
    enum_values: list[Any] | None = None
    is_optional: bool = False
    annotation: Any | None = None
    item_annotation: Any | None = None
    metadata: tuple[Any, ...] = ()
    has_default: bool = False
    default_value: Any = None
    default_factory: Callable[[], Any] | None = None
    examples: tuple[Any, ...] = ()


@dataclass(slots=True)
class _SimpleFieldInfo:
    annotation: Any
    metadata: tuple[Any, ...]
    default: Any
    default_factory: Callable[[], Any] | None
    examples: tuple[Any, ...] = ()


FieldInfoLike = FieldInfo | _SimpleFieldInfo


def extract_constraints(field: FieldInfoLike) -> FieldConstraints:
    """Extract constraint metadata from a single Pydantic FieldInfo."""
    constraints = FieldConstraints()

    for meta in field.metadata:
        _apply_metadata(constraints, meta)

    # Additional decimal info can be provided via annotation / metadata
    _normalize_decimal_constraints(constraints)

    return constraints


def extract_model_constraints(model: type[BaseModel]) -> Mapping[str, FieldConstraints]:
    """Return constraint metadata for each field on a Pydantic model."""
    result: dict[str, FieldConstraints] = {}
    for name, field in model.model_fields.items():
        constraints = extract_constraints(field)
        if constraints.has_constraints():
            result[name] = constraints
    return result


def summarize_field(field: FieldInfoLike) -> FieldSummary:
    constraints = extract_constraints(field)
    annotation = field.annotation
    summary = _summarize_annotation(annotation, constraints, metadata=tuple(field.metadata))
    if field.default is not PydanticUndefined:
        summary.has_default = True
        summary.default_value = field.default
    default_factory = getattr(field, "default_factory", PydanticUndefined)
    if default_factory is not None and default_factory is not PydanticUndefined:
        summary.default_factory = cast(Callable[[], Any], default_factory)
    examples = getattr(field, "examples", None)
    if examples:
        summary.examples = tuple(examples)
    return summary


def summarize_model_fields(model: type[Any]) -> Mapping[str, FieldSummary]:
    summary: dict[str, FieldSummary] = {}
    field_map: Mapping[str, FieldInfo | _SimpleFieldInfo]

    model_fields = getattr(model, "model_fields", None)
    if isinstance(model_fields, Mapping):
        field_map = model_fields
    elif is_dataclass_type(model):
        field_map = _dataclass_field_info_map(model)
    elif is_typeddict_type(model):
        field_map = _typeddict_field_info_map(model)
    else:
        raise TypeError(f"Unsupported model type: {model!r}")

    for name, field in field_map.items():
        summary[name] = summarize_field(field)
    return summary


def _dataclass_field_info_map(model: type[Any]) -> Mapping[str, _SimpleFieldInfo]:
    annotations = get_type_hints(model, include_extras=True)
    result: dict[str, _SimpleFieldInfo] = {}
    for field in dataclasses_module.fields(model):
        if not field.init:
            continue
        annotation = annotations.get(field.name, field.type)
        metadata_entries = tuple(field.metadata.values()) if field.metadata else ()
        default_value: Any = PydanticUndefined
        default_factory: Callable[[], Any] | None = None
        if field.default is not dataclasses_module.MISSING:
            default_value = field.default
        else:
            default_factory_attr = getattr(field, "default_factory", dataclasses_module.MISSING)
            if default_factory_attr is not dataclasses_module.MISSING:
                default_factory = cast(Callable[[], Any], default_factory_attr)
        result[field.name] = _SimpleFieldInfo(
            annotation=annotation,
            metadata=metadata_entries,
            default=default_value,
            default_factory=default_factory,
        )
    return result


def _typeddict_field_info_map(model: type[Any]) -> Mapping[str, _SimpleFieldInfo]:
    annotations = get_type_hints(model, include_extras=True)
    result: dict[str, _SimpleFieldInfo] = {}
    for field_name, annotation in annotations.items():
        origin = get_origin(annotation)
        required = True
        if origin in (Required, NotRequired):
            required = origin is Required
            annotation = get_args(annotation)[0]

        metadata: tuple[Any, ...] = ()
        if required:
            default_value: Any = getattr(model, field_name, PydanticUndefined)
        else:
            default_value = getattr(model, field_name, None)
            annotation = annotation | type(None)

        result[field_name] = _SimpleFieldInfo(
            annotation=annotation,
            metadata=metadata,
            default=default_value,
            default_factory=None,
        )
    return result


def _apply_metadata(constraints: FieldConstraints, meta: Any) -> None:
    # Numeric bounds
    if meta is None:
        return

    if isinstance(meta, annotated_types.Interval):
        constraints.ge = _max_value(constraints.ge, _to_float(getattr(meta, "ge", None)))
        constraints.le = _min_value(constraints.le, _to_float(getattr(meta, "le", None)))
        constraints.gt = _max_value(constraints.gt, _to_float(getattr(meta, "gt", None)))
        constraints.lt = _min_value(constraints.lt, _to_float(getattr(meta, "lt", None)))

    if isinstance(meta, annotated_types.Ge):
        constraints.ge = _max_value(constraints.ge, _to_float(meta.ge))
    if isinstance(meta, annotated_types.Le):
        constraints.le = _min_value(constraints.le, _to_float(meta.le))
    if hasattr(annotated_types, "Gt") and isinstance(meta, annotated_types.Gt):
        constraints.gt = _max_value(constraints.gt, _to_float(getattr(meta, "gt", None)))
    if hasattr(annotated_types, "Lt") and isinstance(meta, annotated_types.Lt):
        constraints.lt = _min_value(constraints.lt, _to_float(getattr(meta, "lt", None)))
    if hasattr(annotated_types, "MultipleOf") and isinstance(meta, annotated_types.MultipleOf):
        constraints.multiple_of = _to_float(getattr(meta, "multiple_of", None))

    # String / collection length
    if isinstance(meta, annotated_types.MinLen):
        constraints.min_length = _max_int(constraints.min_length, meta.min_length)
    if isinstance(meta, annotated_types.MaxLen):
        constraints.max_length = _min_int(constraints.max_length, meta.max_length)

    # General metadata container used by Pydantic for Field(...)
    if hasattr(meta, "__dict__"):
        data = meta.__dict__
        if "pattern" in data and data["pattern"] is not None:
            constraints.pattern = data["pattern"]
        if "min_length" in data and data["min_length"] is not None:
            constraints.min_length = _max_int(constraints.min_length, data["min_length"])
        if "max_length" in data and data["max_length"] is not None:
            constraints.max_length = _min_int(constraints.max_length, data["max_length"])
        if "max_digits" in data and data["max_digits"] is not None:
            constraints.max_digits = _min_int(constraints.max_digits, data["max_digits"])
        if "decimal_places" in data and data["decimal_places"] is not None:
            constraints.decimal_places = _min_int(
                constraints.decimal_places, data["decimal_places"]
            )


def _normalize_decimal_constraints(constraints: FieldConstraints) -> None:
    if (
        constraints.max_digits is not None
        and constraints.decimal_places is not None
        and constraints.decimal_places > constraints.max_digits
    ):
        constraints.decimal_places = constraints.max_digits


def _max_value(current: float | None, new: float | int | decimal.Decimal | None) -> float | None:
    if new is None:
        return current
    new_float = float(new)
    if current is None or new_float > current:
        return new_float
    return current


def _min_value(current: float | None, new: float | int | decimal.Decimal | None) -> float | None:
    if new is None:
        return current
    new_float = float(new)
    if current is None or new_float < current:
        return new_float
    return current


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return None


def _max_int(current: int | None, new: int | None) -> int | None:
    if new is None:
        return current
    if current is None or new > current:
        return int(new)
    return current


def _min_int(current: int | None, new: int | None) -> int | None:
    if new is None:
        return current
    if current is None or new < current:
        return int(new)
    return current


def _strip_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin in {Union, types.UnionType}:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]  # noqa: E721
        if len(args) == 1 and len(get_args(annotation)) != len(args):
            return args[0], True
    return annotation, False


def _extract_enum_values(annotation: Any) -> list[Any] | None:
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return [member.value for member in annotation]
    origin = get_origin(annotation)
    if origin is Literal:
        return list(get_args(annotation))
    return None


def _summarize_annotation(
    annotation: Any,
    constraints: FieldConstraints | None = None,
    *,
    metadata: tuple[Any, ...] | None = None,
) -> FieldSummary:
    inner_annotation, is_optional = _strip_optional(annotation)
    type_name, fmt, item_annotation = _infer_annotation_kind(inner_annotation)
    item_type = None
    item_annotation_clean = None
    if item_annotation is not None:
        item_inner, _ = _strip_optional(item_annotation)
        item_annotation_clean = item_inner
        item_type, _, _ = _infer_annotation_kind(item_inner)
    enum_values = _extract_enum_values(inner_annotation)
    return FieldSummary(
        type=type_name,
        constraints=constraints or FieldConstraints(),
        format=fmt,
        item_type=item_type,
        enum_values=enum_values,
        is_optional=is_optional,
        annotation=inner_annotation,
        item_annotation=item_annotation_clean,
        metadata=metadata or (),
    )


def _infer_annotation_kind(annotation: Any) -> tuple[str, str | None, Any | None]:
    annotation = _unwrap_annotation(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {Union, types.UnionType}:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
        if len(non_none) == 1:
            return _infer_annotation_kind(non_none[0])

    if origin is Literal:
        return "enum", None, None

    if origin in {list, list[int]}:  # pragma: no cover - typing quirk
        origin = list

    if origin in {list, set, tuple}:
        item_annotation = args[0] if args else None
        type_map = {list: "list", set: "set", tuple: "tuple"}
        return type_map.get(origin, "collection"), None, item_annotation

    if origin in {dict}:
        value_annotation = args[1] if len(args) > 1 else None
        return "mapping", None, value_annotation

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return "enum", None, None

    if _np is not None:
        ndarray_type = getattr(_np, "ndarray", None)
        if ndarray_type is not None:
            if origin is ndarray_type:
                dtype_name = None
                if args:
                    for candidate in args:
                        if (
                            isinstance(candidate, types.GenericAlias)
                            and getattr(candidate, "__origin__", None) is tuple
                        ):
                            continue
                        dtype_name = _resolve_numpy_dtype_name(candidate)
                        if dtype_name is not None:
                            break
                return "numpy-array", dtype_name, None
            if isinstance(annotation, type) and issubclass(annotation, ndarray_type):
                return "numpy-array", None, None

    if annotation is Any:
        return "any", None, None

    if isinstance(annotation, type):
        extra_type_id = resolve_type_id(annotation)
        if extra_type_id is not None:
            return extra_type_id, None, None
        if dataclasses_module.is_dataclass(annotation):
            return "dataclass", None, None
        if is_typeddict_type(annotation):
            return "typed-dict", None, None
        if _matches_pydantic_type(annotation, "EmailStr"):
            return "email", None, None
        if _matches_pydantic_type(annotation, "AnyUrl"):
            return "url", None, None
        if _matches_pydantic_type(annotation, "IPvAnyAddress"):
            return "ip-address", None, None
        if _matches_pydantic_type(annotation, "IPvAnyInterface"):
            return "ip-interface", None, None
        if _matches_pydantic_type(annotation, "IPvAnyNetwork"):
            return "ip-network", None, None
        path_match = _match_path_annotation(annotation)
        if path_match is not None:
            return path_match
        if issubclass(annotation, SecretStr):
            return "secret-str", None, None
        if issubclass(annotation, SecretBytes):
            return "secret-bytes", None, None
        if issubclass(annotation, uuid.UUID):
            return "uuid", None, None
        if issubclass(annotation, datetime.datetime):
            return "datetime", None, None
        if issubclass(annotation, datetime.date) and not issubclass(annotation, datetime.datetime):
            return "date", None, None
        if issubclass(annotation, datetime.time):
            return "time", None, None
        if _looks_like_pydantic_model(annotation):
            return "model", None, None
        scalar_map = {
            bool: "bool",
            int: "int",
            float: "float",
            str: "string",
            bytes: "bytes",
            decimal.Decimal: "decimal",
        }
        for candidate, label in scalar_map.items():
            if issubclass(annotation, candidate):
                return label, None, None

    return "any", None, None


def _unwrap_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(get_args(annotation)[0])
    forward_arg = getattr(annotation, "__forward_arg__", None)
    if isinstance(forward_arg, str):
        resolved = _resolve_forward_ref(forward_arg)
        if resolved is not None:
            return resolved
    if isinstance(annotation, str):
        candidate = getattr(pydantic, annotation, None)
        if isinstance(candidate, type):
            return candidate
    return annotation


def _match_path_annotation(annotation: type[Any]) -> tuple[str, str | None, Any | None] | None:
    directory_path_type = getattr(pydantic, "DirectoryPath", None)
    file_path_type = getattr(pydantic, "FilePath", None)
    for path_type, path_kind in ((file_path_type, "file"), (directory_path_type, "directory")):
        if path_type is None:
            continue
        path_cls = _unwrap_annotation(path_type)
        if isinstance(path_cls, type) and issubclass(annotation, path_cls):
            return "path", path_kind, None

    for attr in ("PurePath", "Path"):
        pathlib_type = getattr(pathlib, attr, None)
        if pathlib_type is not None and issubclass(annotation, pathlib_type):
            return "path", None, None

    return None


def _resolve_forward_ref(target: str) -> Any | None:
    resolved = resolve_forward_ref(target)
    if resolved is not None:
        return resolved
    candidate = getattr(pydantic, target, None)
    if isinstance(candidate, type):
        return candidate
    return None


def _matches_pydantic_type(annotation: type[Any], attr: str) -> bool:
    candidate = getattr(pydantic, attr, None)
    if isinstance(candidate, type):
        try:
            if issubclass(annotation, candidate):
                return True
        except TypeError:
            pass
    module = getattr(annotation, "__module__", "")
    name = getattr(annotation, "__name__", "")
    return module.startswith("pydantic") and name == attr


def _looks_like_pydantic_model(annotation: Any) -> bool:
    if not isinstance(annotation, type):
        return False
    try:
        if issubclass(annotation, BaseModel):
            return True
    except TypeError:
        pass
    return hasattr(annotation, "model_fields") or hasattr(annotation, "__fields__")


def _resolve_numpy_dtype_name(arg: Any) -> str | None:
    if _np is None:
        return None
    if isinstance(arg, types.GenericAlias):
        alias_args = getattr(arg, "__args__", ())
        if alias_args:
            return _resolve_numpy_dtype_name(alias_args[0])
        return None
    try:
        dtype_obj = _np.dtype(arg)
    except Exception:  # pragma: no cover - defensive
        return None
    name = getattr(dtype_obj, "name", None)
    if isinstance(name, str):
        return name
    return str(dtype_obj)
