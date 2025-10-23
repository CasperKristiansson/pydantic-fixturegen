"""Utilities for extracting constraint metadata from Pydantic models."""

from __future__ import annotations

import datetime
import decimal
import enum
import types
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Union, get_args, get_origin

import annotated_types
import pydantic
from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic.fields import FieldInfo


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


def extract_constraints(field: FieldInfo) -> FieldConstraints:
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


def summarize_field(field: FieldInfo) -> FieldSummary:
    constraints = extract_constraints(field)
    annotation = field.annotation
    inner_annotation, is_optional = _strip_optional(annotation)
    type_name, fmt, item_annotation = _infer_annotation_kind(inner_annotation)
    item_type = None
    if item_annotation is not None:
        item_type, _, _ = _infer_annotation_kind(item_annotation)
    enum_values = _extract_enum_values(inner_annotation)
    return FieldSummary(
        type=type_name,
        constraints=constraints,
        format=fmt,
        item_type=item_type,
        enum_values=enum_values,
        is_optional=is_optional,
    )


def summarize_model_fields(model: type[BaseModel]) -> Mapping[str, FieldSummary]:
    summary: dict[str, FieldSummary] = {}
    for name, field in model.model_fields.items():
        summary[name] = summarize_field(field)
    return summary


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
    return None


def _infer_annotation_kind(annotation: Any) -> tuple[str, str | None, Any | None]:
    annotation = _unwrap_annotation(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {Union, types.UnionType}:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
        if len(non_none) == 1:
            return _infer_annotation_kind(non_none[0])

    if origin in {list, list[int]}:  # pragma: no cover - typing quirk
        origin = list

    if origin in {list, set, tuple}:
        item_annotation = args[0] if args else None
        type_map = {list: "list", set: "set", tuple: "tuple"}
        return type_map.get(origin, "collection"), None, item_annotation

    if origin in {dict}:
        return "mapping", None, None

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return "enum", None, None

    if annotation is Any:
        return "any", None, None

    if isinstance(annotation, type):
        email_type = getattr(pydantic, "EmailStr", None)
        if email_type is not None and issubclass(annotation, email_type):
            return "email", None, None
        any_url_type = getattr(pydantic, "AnyUrl", None)
        if any_url_type is not None and issubclass(annotation, any_url_type):
            return "url", None, None
        ip_address_type = getattr(pydantic, "IPvAnyAddress", None)
        if ip_address_type is not None and issubclass(annotation, ip_address_type):
            return "ip-address", None, None
        ip_interface_type = getattr(pydantic, "IPvAnyInterface", None)
        if ip_interface_type is not None and issubclass(annotation, ip_interface_type):
            return "ip-interface", None, None
        ip_network_type = getattr(pydantic, "IPvAnyNetwork", None)
        if ip_network_type is not None and issubclass(annotation, ip_network_type):
            return "ip-network", None, None
        payment_card_type = getattr(pydantic, "PaymentCardNumber", None)
        if payment_card_type is not None and issubclass(annotation, payment_card_type):
            return "payment-card", None, None
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
        if issubclass(annotation, BaseModel):
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
    return annotation
