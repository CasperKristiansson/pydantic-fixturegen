"""Hookspec definitions for pydantic-fixturegen plugins."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:  # pragma: no cover
    from pydantic import BaseModel
    from pydantic_fixturegen.core.providers import ProviderRegistry
    from pydantic_fixturegen.core.strategies import Strategy

hookspec = pluggy.HookspecMarker("pfg")
hookimpl = pluggy.HookimplMarker("pfg")


@dataclass(slots=True)
class EmitterContext:
    """Context passed to emitter plugins."""

    models: Sequence[type[BaseModel]]
    output: Path
    parameters: Mapping[str, object]


@hookspec
def pfg_register_providers(registry: ProviderRegistry) -> None:  # pragma: no cover
    """Register additional providers with the given registry."""


@hookspec
def pfg_modify_strategy(
    model: type[BaseModel],
    field_name: str,
    strategy: Strategy,
) -> Strategy | None:  # pragma: no cover
    """Modify or replace the strategy chosen for a model field."""


@hookspec
def pfg_emit_artifact(kind: str, context: EmitterContext) -> bool:  # pragma: no cover
    """Handle artifact emission for ``kind``. Return True to skip default behaviour."""


__all__ = [
    "EmitterContext",
    "hookimpl",
    "hookspec",
    "pfg_emit_artifact",
    "pfg_modify_strategy",
    "pfg_register_providers",
]
