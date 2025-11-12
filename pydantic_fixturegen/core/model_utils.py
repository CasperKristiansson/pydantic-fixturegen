"""Shared helpers for inspecting supported model families and serialization."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter
from typing_extensions import is_typeddict  # type: ignore[attr-defined]


def is_pydantic_model(model_cls: type[Any]) -> bool:
    try:
        return issubclass(model_cls, BaseModel)
    except TypeError:
        return False


def is_dataclass_type(model_cls: Any) -> bool:
    return dataclasses.is_dataclass(model_cls)


def is_typeddict_type(model_cls: Any) -> bool:
    try:
        return is_typeddict(model_cls)
    except Exception:  # pragma: no cover - typing differences between versions
        return False


@lru_cache(maxsize=256)
def _type_adapter_for(model_cls: type[Any]) -> TypeAdapter[Any]:
    return TypeAdapter(model_cls)


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
        return schema_func()
    adapter = _type_adapter_for(model_cls)
    return adapter.json_schema()

__all__ = [
    "dump_model_instance",
    "is_dataclass_type",
    "is_pydantic_model",
    "is_typeddict_type",
    "model_json_schema",
]
