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

DEFAULT_PYTEST_STYLE = cast(Literal["functions", "factory", "class"], DEFAULT_CONFIG.emitters.pytest.style)
DEFAULT_PYTEST_SCOPE = cast(Literal["function", "module", "session"], DEFAULT_CONFIG.emitters.pytest.scope)
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


class ConfigSchemaModel(BaseModel):
    """Authoritative schema for `[tool.pydantic_fixturegen]` configuration."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        title="pydantic-fixturegen configuration",
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
