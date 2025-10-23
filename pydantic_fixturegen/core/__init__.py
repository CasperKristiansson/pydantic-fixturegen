"""Core utilities for pydantic-fixturegen."""

from .ast_discover import AstDiscoveryResult, AstModel, discover_models
from .config import (
    AppConfig,
    ConfigError,
    EmittersConfig,
    JsonConfig,
    PytestEmitterConfig,
    load_config,
)
from .introspect import IntrospectedModel, IntrospectionResult
from .introspect import discover as introspect
from .providers import ProviderRef, ProviderRegistry
from .providers.strings import generate_string, register_string_providers
from .safe_import import SafeImportResult, safe_import_models
from .schema import (
    FieldConstraints,
    FieldSummary,
    extract_constraints,
    extract_model_constraints,
    summarize_field,
    summarize_model_fields,
)
from .seed import SeedManager
from .version import build_artifact_header, get_tool_version

__all__ = [
    "AppConfig",
    "AstDiscoveryResult",
    "AstModel",
    "ConfigError",
    "EmittersConfig",
    "JsonConfig",
    "PytestEmitterConfig",
    "SafeImportResult",
    "SeedManager",
    "FieldConstraints",
    "FieldSummary",
    "ProviderRef",
    "ProviderRegistry",
    "generate_string",
    "register_string_providers",
    "build_artifact_header",
    "discover_models",
    "introspect",
    "IntrospectedModel",
    "IntrospectionResult",
    "get_tool_version",
    "load_config",
    "extract_constraints",
    "extract_model_constraints",
    "summarize_field",
    "summarize_model_fields",
    "safe_import_models",
]
