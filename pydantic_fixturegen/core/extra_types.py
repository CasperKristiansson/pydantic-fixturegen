"""Metadata helpers for optional `pydantic-extra-types` integrations."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, get_args, get_origin

__all__ = [
    "ExtraTypeEntry",
    "AVAILABLE_EXTRA_TYPE_IDS",
    "available_type_ids",
    "describe_extra_annotation",
    "is_extra_annotation",
    "iter_available_types",
    "resolve_type_id",
]


@dataclass(frozen=True)
class ExtraTypeEntry:
    """Descriptor for a pydantic-extra-types class we know how to handle."""

    type_id: str
    module: str
    attr: str


_ENTRIES: tuple[ExtraTypeEntry, ...] = (
    ExtraTypeEntry("color", "pydantic_extra_types.color", "Color"),
    ExtraTypeEntry("latitude", "pydantic_extra_types.coordinate", "Latitude"),
    ExtraTypeEntry("longitude", "pydantic_extra_types.coordinate", "Longitude"),
    ExtraTypeEntry("coordinate", "pydantic_extra_types.coordinate", "Coordinate"),
    ExtraTypeEntry("country-alpha2", "pydantic_extra_types.country", "CountryAlpha2"),
    ExtraTypeEntry("country-alpha3", "pydantic_extra_types.country", "CountryAlpha3"),
    ExtraTypeEntry("country-numeric", "pydantic_extra_types.country", "CountryNumericCode"),
    ExtraTypeEntry("cron", "pydantic_extra_types.cron", "CronStr"),
    ExtraTypeEntry("currency-iso4217", "pydantic_extra_types.currency_code", "ISO4217"),
    ExtraTypeEntry("currency", "pydantic_extra_types.currency_code", "Currency"),
    ExtraTypeEntry("domain", "pydantic_extra_types.domain", "DomainStr"),
    ExtraTypeEntry("epoch-number", "pydantic_extra_types.epoch", "Number"),
    ExtraTypeEntry("epoch-integer", "pydantic_extra_types.epoch", "Integer"),
    ExtraTypeEntry("isbn", "pydantic_extra_types.isbn", "ISBN"),
    ExtraTypeEntry("language-alpha2", "pydantic_extra_types.language_code", "LanguageAlpha2"),
    ExtraTypeEntry("language-name", "pydantic_extra_types.language_code", "LanguageName"),
    ExtraTypeEntry("language-iso639-3", "pydantic_extra_types.language_code", "ISO639_3"),
    ExtraTypeEntry("language-iso639-5", "pydantic_extra_types.language_code", "ISO639_5"),
    ExtraTypeEntry("mac-address", "pydantic_extra_types.mac_address", "MacAddress"),
    ExtraTypeEntry("mongo-object-id", "pydantic_extra_types.mongo_object_id", "MongoObjectId"),
    ExtraTypeEntry("mongo-object-id", "beanie.odm.fields", "PydanticObjectId"),
    ExtraTypeEntry("payment-card", "pydantic_extra_types.payment", "PaymentCardNumber"),
    ExtraTypeEntry("pendulum-datetime", "pydantic_extra_types.pendulum_dt", "DateTime"),
    ExtraTypeEntry("pendulum-time", "pydantic_extra_types.pendulum_dt", "Time"),
    ExtraTypeEntry("pendulum-date", "pydantic_extra_types.pendulum_dt", "Date"),
    ExtraTypeEntry("pendulum-duration", "pydantic_extra_types.pendulum_dt", "Duration"),
    ExtraTypeEntry("phone-number", "pydantic_extra_types.phone_numbers", "PhoneNumber"),
    ExtraTypeEntry("routing-number", "pydantic_extra_types.routing_number", "ABARoutingNumber"),
    ExtraTypeEntry("s3-path", "pydantic_extra_types.s3", "S3Path"),
    ExtraTypeEntry("script-code", "pydantic_extra_types.script_code", "ISO_15924"),
    ExtraTypeEntry("semantic-version", "pydantic_extra_types.semantic_version", "SemanticVersion"),
    ExtraTypeEntry("semantic-version", "semver", "Version"),
    ExtraTypeEntry("timezone-name", "pydantic_extra_types.timezone_name", "TimeZoneName"),
    ExtraTypeEntry("ulid", "pydantic_extra_types.ulid", "ULID"),
    ExtraTypeEntry("slug", "pydantic_extra_types.slug", "SlugStr"),
)

_MODULE_CACHE: dict[str, Any | None] = {}
_CLASS_TO_ID: dict[type[Any], str] = {}
_TYPE_ID_TO_CLASSES: dict[str, list[type[Any]]] = {}


def _import_module(name: str) -> Any | None:
    cached = _MODULE_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        module = importlib.import_module(name)
    except (ImportError, RuntimeError):  # optional dependency missing
        module = None
    _MODULE_CACHE[name] = module
    return module


for entry in _ENTRIES:
    module = _import_module(entry.module)
    if module is None:
        continue
    cls = getattr(module, entry.attr, None)
    if not isinstance(cls, type):
        continue
    _CLASS_TO_ID[cls] = entry.type_id
    bucket = _TYPE_ID_TO_CLASSES.setdefault(entry.type_id, [])
    bucket.append(cls)


AVAILABLE_EXTRA_TYPE_IDS: frozenset[str] = frozenset(_TYPE_ID_TO_CLASSES.keys())


def iter_available_types() -> Mapping[str, tuple[type[Any], ...]]:
    """Return a snapshot of available extra-type classes keyed by type identifier."""

    return {type_id: tuple(classes) for type_id, classes in _TYPE_ID_TO_CLASSES.items()}


def resolve_type_id(annotation: Any) -> str | None:
    """Return the registered type identifier for ``annotation`` if it matches an extra type."""

    if not isinstance(annotation, type):
        return None

    for cls, type_id in _CLASS_TO_ID.items():
        try:
            if issubclass(annotation, cls):
                return type_id
        except TypeError:  # pragma: no cover - annotation not suitable for issubclass
            continue
    return None


def describe_extra_annotation(annotation: Any) -> str | None:
    """Return a human-readable label when the annotation originates from extra types."""

    stack = [annotation]
    seen: set[int] = set()

    while stack:
        target = stack.pop()
        target_id = id(target)
        if target_id in seen:
            continue
        seen.add(target_id)

        module = getattr(target, "__module__", "")
        if module.startswith("pydantic_extra_types"):
            name = getattr(target, "__qualname__", getattr(target, "__name__", str(target)))
            return f"{module}.{name}"

        origin = get_origin(target)
        if origin is not None:
            stack.append(origin)
        for arg in get_args(target):
            stack.append(arg)

    return None


def is_extra_annotation(annotation: Any) -> bool:
    """Return True if annotation comes from the pydantic-extra-types namespace."""

    return describe_extra_annotation(annotation) is not None


def available_type_ids() -> Iterable[str]:
    return AVAILABLE_EXTRA_TYPE_IDS
