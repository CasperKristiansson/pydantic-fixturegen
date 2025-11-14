"""Shared helpers for inspecting supported model families and serialization."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter

try:  # typing_extensions < 4.5 compatibility
    from typing_extensions import is_typeddict as _typing_extensions_is_typeddict
except ImportError:  # pragma: no cover - typing extra not installed
    def _typing_extensions_is_typeddict(tp: object) -> bool:
        return False


def is_pydantic_model(model_cls: type[Any]) -> bool:
    try:
        return issubclass(model_cls, BaseModel)
    except TypeError:
        return False


def is_dataclass_type(model_cls: Any) -> bool:
    return dataclasses.is_dataclass(model_cls)


def is_typeddict_type(model_cls: Any) -> bool:
    try:
        return _typing_extensions_is_typeddict(model_cls)
    except Exception:  # pragma: no cover - typing differences between versions
        return False


_TYPE_ADAPTER_CACHE: dict[type[Any], TypeAdapter[Any]] = {}


def _type_adapter_for(model_cls: type[Any]) -> TypeAdapter[Any]:
    adapter = _TYPE_ADAPTER_CACHE.get(model_cls)
    if adapter is None:
        adapter = TypeAdapter(model_cls)
        _TYPE_ADAPTER_CACHE[model_cls] = adapter
    return adapter


def dump_model_instance(
    model_cls: type[Any],
    instance: Any,
    *,
    mode: Literal["python", "json"] = "python",
) -> dict[str, Any]:
    """Serialize ``instance`` according to ``mode`` regardless of model family."""

    if isinstance(instance, BaseModel):
        payload: Any = instance.model_dump(mode=mode)
    else:
        adapter = _type_adapter_for(model_cls)
        payload = adapter.dump_python(instance, mode=mode)

    if isinstance(payload, dict):
        return payload
    if isinstance(payload, Mapping):
        return dict(payload)
    raise TypeError(
        f"Expected mapping payload for {model_cls.__qualname__}, got {type(payload).__qualname__}."
    )


def model_json_schema(model_cls: type[Any]) -> dict[str, Any]:
    """Return the JSON schema for ``model_cls`` regardless of implementation."""

    schema_func = getattr(model_cls, "model_json_schema", None)
    if callable(schema_func):
        schema = schema_func()
    else:
        adapter = _type_adapter_for(model_cls)
        schema = adapter.json_schema()

    if isinstance(schema, Mapping):
        return dict(schema)
    raise TypeError(
        f"Expected mapping schema for {model_cls.__qualname__}, got {type(schema).__qualname__}."
    )


__all__ = [
    "dump_model_instance",
    "is_dataclass_type",
    "is_pydantic_model",
    "is_typeddict_type",
    "model_json_schema",
]
