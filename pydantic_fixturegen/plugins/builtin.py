"""Built-in plugin registrations exposed via entry points."""

from __future__ import annotations

from pydantic_fixturegen.core.providers import (
    register_collection_providers,
    register_identifier_providers,
    register_numeric_providers,
    register_string_providers,
    register_temporal_providers,
)
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.plugins.hookspecs import hookimpl

_SENTINEL_KEYS = {
    "numbers": "int",
    "strings": "string",
    "collections": "list",
    "temporal": "datetime",
    "identifiers": "email",
}


def _ensure_registered(registry: ProviderRegistry, key: str, register_func) -> None:
    if registry.get(key) is None:
        register_func(registry)


@hookimpl
def pfg_register_providers(registry: ProviderRegistry) -> None:
    """Register built-in providers when entry point loading is used."""

    _ensure_registered(registry, _SENTINEL_KEYS["numbers"], register_numeric_providers)
    _ensure_registered(registry, _SENTINEL_KEYS["strings"], register_string_providers)
    _ensure_registered(registry, _SENTINEL_KEYS["collections"], register_collection_providers)
    _ensure_registered(registry, _SENTINEL_KEYS["temporal"], register_temporal_providers)
    _ensure_registered(registry, _SENTINEL_KEYS["identifiers"], register_identifier_providers)


__all__ = ["pfg_register_providers"]
