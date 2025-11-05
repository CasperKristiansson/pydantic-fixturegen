"""Provider registry and built-in providers."""

from .collections import register_collection_providers
from .identifiers import register_identifier_providers
from .numbers import register_numeric_providers
from .numpy_arrays import register_numpy_array_providers
from .registry import ProviderRef, ProviderRegistry
from .strings import register_string_providers
from .temporal import register_temporal_providers


def create_default_registry(load_plugins: bool = True) -> ProviderRegistry:
    registry = ProviderRegistry()
    register_numeric_providers(registry)
    register_string_providers(registry)
    register_collection_providers(registry)
    register_temporal_providers(registry)
    register_identifier_providers(registry)
    register_numpy_array_providers(registry)
    if load_plugins:
        registry.load_entrypoint_plugins()
    return registry


__all__ = [
    "ProviderRef",
    "ProviderRegistry",
    "create_default_registry",
    "register_string_providers",
    "register_numeric_providers",
    "register_collection_providers",
    "register_temporal_providers",
    "register_identifier_providers",
    "register_numpy_array_providers",
]
