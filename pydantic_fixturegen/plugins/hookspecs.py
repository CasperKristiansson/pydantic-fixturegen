"""Hookspec definitions for pydantic-fixturegen plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:  # pragma: no cover
    from pydantic_fixturegen.core.providers import ProviderRegistry

hookspec = pluggy.HookspecMarker("pfg")
hookimpl = pluggy.HookimplMarker("pfg")


@hookspec
def pfg_register_providers(registry: ProviderRegistry) -> None:  # pragma: no cover
    """Register additional providers with the given registry."""


__all__ = ["hookspec", "hookimpl", "pfg_register_providers"]
