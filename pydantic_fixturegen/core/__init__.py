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
from .providers import (
    ProviderRef,
    ProviderRegistry,
    create_default_registry,
    register_collection_providers,
    register_identifier_providers,
    register_numeric_providers,
    register_string_providers,
    register_temporal_providers,
)
from .generate import GenerationConfig, InstanceGenerator
from .providers.collections import generate_collection
from .providers.identifiers import generate_identifier
from .providers.numbers import generate_numeric
from .providers.strings import generate_string
from .providers.temporal import generate_temporal
from .io_utils import WriteResult, write_atomic_bytes, write_atomic_text
from .safe_import import SafeImportResult, safe_import_models
from .schema import (
    FieldConstraints,
    FieldSummary,
    extract_constraints,
    extract_model_constraints,
    summarize_field,
    summarize_model_fields,
)
from .strategies import Strategy, StrategyBuilder, UnionStrategy
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
    "WriteResult",
    "FieldConstraints",
    "FieldSummary",
    "ProviderRef",
    "ProviderRegistry",
    "Strategy",
    "StrategyBuilder",
    "UnionStrategy",
    "create_default_registry",
    "generate_collection",
    "generate_identifier",
    "generate_numeric",
    "generate_string",
    "generate_temporal",
    "GenerationConfig",
    "InstanceGenerator",
    "register_string_providers",
    "register_numeric_providers",
    "register_collection_providers",
    "register_identifier_providers",
    "register_temporal_providers",
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
    "write_atomic_text",
    "write_atomic_bytes",
]
