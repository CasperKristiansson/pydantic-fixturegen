"""JSON Schema generation for pydantic-fixturegen configuration."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .config import DEFAULT_CONFIG
from .seed import DEFAULT_LOCALE

SCHEMA_ID = "https://raw.githubusercontent.com/CasperKristiansson/pydantic-fixturegen/main/pydantic_fixturegen/schemas/config.schema.json"
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


UnionPolicyLiteral = Literal["first", "random", "weighted"]
EnumPolicyLiteral = Literal["first", "random"]

DEFAULT_PYTEST_STYLE = cast(
    Literal["functions", "factory", "class"],
    DEFAULT_CONFIG.emitters.pytest.style,
)
DEFAULT_PYTEST_SCOPE = cast(
    Literal["function", "module", "session"],
    DEFAULT_CONFIG.emitters.pytest.scope,
)
DEFAULT_UNION_POLICY = cast(UnionPolicyLiteral, DEFAULT_CONFIG.union_policy)
DEFAULT_ENUM_POLICY = cast(EnumPolicyLiteral, DEFAULT_CONFIG.enum_policy)


class PytestEmitterSchema(BaseModel):
    """Schema for pytest emitter settings."""

    model_config = ConfigDict(extra="forbid")

    style: Literal["functions", "factory", "class"] = Field(
        default=DEFAULT_PYTEST_STYLE,
        description="How emitted pytest fixtures are structured.",
    )
    scope: Literal["function", "module", "session"] = Field(
        default=DEFAULT_PYTEST_SCOPE,
        description="Default pytest fixture scope.",
    )


class EmittersSchema(BaseModel):
    """Schema for emitter configuration sections."""

    model_config = ConfigDict(extra="forbid")

    pytest: PytestEmitterSchema = Field(
        default_factory=PytestEmitterSchema,
        description="Configuration for the built-in pytest fixture emitter.",
    )


class JsonSchema(BaseModel):
    """Schema for JSON emitter settings."""

    model_config = ConfigDict(extra="forbid")

    indent: int = Field(
        default=DEFAULT_CONFIG.json.indent,
        ge=0,
        description="Indentation level for JSON output (0 for compact).",
    )
    orjson: bool = Field(
        default=DEFAULT_CONFIG.json.orjson,
        description="Use orjson for serialization when available.",
    )


class FieldPolicyOptionsSchema(BaseModel):
    """Schema describing supported field policy overrides."""

    model_config = ConfigDict(extra="forbid")

    p_none: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Probability override for returning None on optional fields.",
    )
    enum_policy: EnumPolicyLiteral | None = Field(
        default=None,
        description="Enum selection policy for matching fields.",
    )
    union_policy: Literal["first", "random"] | None = Field(
        default=None,
        description="Union selection policy for matching fields.",
    )


class ArraySettingsSchema(BaseModel):
    """Schema describing NumPy array generation settings."""

    model_config = ConfigDict(extra="forbid")

    max_ndim: int = Field(
        default=DEFAULT_CONFIG.arrays.max_ndim,
        ge=1,
        description="Maximum number of dimensions for generated arrays.",
    )
    max_side: int = Field(
        default=DEFAULT_CONFIG.arrays.max_side,
        ge=1,
        description="Maximum size per dimension for generated arrays.",
    )
    max_elements: int = Field(
        default=DEFAULT_CONFIG.arrays.max_elements,
        ge=1,
        description="Maximum total element count for generated arrays.",
    )
    dtypes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CONFIG.arrays.dtypes),
        min_length=1,
        description="Allowed NumPy dtypes (strings accepted by numpy.dtype).",
    )


class ConfigSchemaModel(BaseModel):
    """Authoritative schema for `[tool.pydantic_fixturegen]` configuration."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        title="pydantic-fixturegen configuration",
    )

    preset: str | None = Field(
        default=DEFAULT_CONFIG.preset,
        description="Curated preset name applied before other configuration (e.g., 'boundary').",
    )
    seed: int | str | None = Field(
        default=DEFAULT_CONFIG.seed,
        description="Global seed controlling deterministic generation. Accepts int or string.",
    )
    locale: str = Field(
        default=DEFAULT_LOCALE,
        description="Default Faker locale used when generating data.",
    )
    include: list[str] = Field(
        default_factory=list,
        description="Glob patterns of fully-qualified model names to include by default.",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Glob patterns of fully-qualified model names to exclude by default.",
    )
    p_none: float | None = Field(
        default=DEFAULT_CONFIG.p_none,
        ge=0.0,
        le=1.0,
        description="Probability of sampling `None` for optional fields when unspecified.",
    )
    union_policy: UnionPolicyLiteral = Field(
        default=DEFAULT_UNION_POLICY,
        description="Strategy for selecting branches of `typing.Union`.",
    )
    enum_policy: EnumPolicyLiteral = Field(
        default=DEFAULT_ENUM_POLICY,
        description="Strategy for selecting enum members.",
    )
    overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-model overrides keyed by fully-qualified model name.",
    )
    emitters: EmittersSchema = Field(
        default_factory=EmittersSchema,
        description="Emitter-specific configuration sections.",
    )
    json_settings: JsonSchema = Field(
        default_factory=JsonSchema,
        alias="json",
        description="Settings shared by JSON-based emitters.",
    )
    field_policies: dict[str, FieldPolicyOptionsSchema] = Field(
        default_factory=dict,
        description=(
            "Field policy definitions keyed by glob or regex patterns that may target model "
            "names or dotted field paths."
        ),
    )
    locales: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of glob or regex patterns (models or fields) to Faker locale identifiers."
        ),
    )
    arrays: ArraySettingsSchema = Field(
        default_factory=ArraySettingsSchema,
        description=(
            "Configuration for NumPy array generation: max_ndim, max_side, max_elements, dtypes."
        ),
    )
    identifiers: IdentifierSettingsSchema = Field(
        default_factory=lambda: IdentifierSettingsSchema(),
        description=(
            "Configuration for identifier providers (secret lengths, URL schemes, UUID version)."
        ),
    )
    paths: PathSettingsSchema = Field(
        default_factory=lambda: PathSettingsSchema(),
        description="Configuration for filesystem path providers.",
    )


class IdentifierSettingsSchema(BaseModel):
    """Schema describing identifier provider settings."""

    model_config = ConfigDict(extra="forbid")

    secret_str_length: int = Field(
        default=DEFAULT_CONFIG.identifiers.secret_str_length,
        ge=1,
        description="Default length for generated SecretStr values.",
    )
    secret_bytes_length: int = Field(
        default=DEFAULT_CONFIG.identifiers.secret_bytes_length,
        ge=1,
        description="Default length for generated SecretBytes values.",
    )
    url_schemes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CONFIG.identifiers.url_schemes),
        min_length=1,
        description="Allowed URL schemes used when generating URLs.",
    )
    url_include_path: bool = Field(
        default=DEFAULT_CONFIG.identifiers.url_include_path,
        description="Include a path component when generating URLs.",
    )
    uuid_version: int = Field(
        default=DEFAULT_CONFIG.identifiers.uuid_version,
        description="UUID version to use (1 or 4).",
        ge=1,
        le=4,
    )


class PathSettingsSchema(BaseModel):
    """Schema describing filesystem path provider settings."""

    model_config = ConfigDict(extra="forbid")

    default_os: str = Field(
        default=DEFAULT_CONFIG.paths.default_os,
        description="Default OS target for generated filesystem paths.",
        enum=["posix", "windows", "mac"],
    )
    models: dict[str, str] = Field(
        default_factory=lambda: {
            pattern: target for pattern, target in DEFAULT_CONFIG.paths.model_targets
        },
        description=(
            "Mapping of glob patterns to OS targets overriding the default (values: 'posix',"
            " 'windows', 'mac')."
        ),
    )


def build_config_schema() -> dict[str, Any]:
    """Return the JSON schema describing the project configuration."""

    schema = ConfigSchemaModel.model_json_schema(by_alias=True)
    schema["$schema"] = SCHEMA_DRAFT
    schema["$id"] = SCHEMA_ID
    schema.setdefault("description", "Configuration options for pydantic-fixturegen")
    return schema


def get_config_schema_json(*, indent: int | None = 2) -> str:
    """Return the configuration schema serialized to JSON."""

    import json

    schema = build_config_schema()
    return json.dumps(schema, indent=indent, sort_keys=True) + ("\n" if indent else "")


__all__ = ["build_config_schema", "get_config_schema_json", "SCHEMA_ID", "SCHEMA_DRAFT"]
