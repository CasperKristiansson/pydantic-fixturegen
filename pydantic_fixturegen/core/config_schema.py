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
CyclePolicyLiteral = Literal["reuse", "stub", "null"]
RngModeLiteral = Literal["portable", "legacy"]
FieldHintModeLiteral = Literal[
    "none",
    "defaults",
    "examples",
    "defaults-then-examples",
    "examples-then-defaults",
]

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
DEFAULT_CYCLE_POLICY = cast(CyclePolicyLiteral, DEFAULT_CONFIG.cycle_policy)
DEFAULT_RNG_MODE = DEFAULT_CONFIG.rng_mode
DEFAULT_NUMBER_DISTRIBUTION = cast(
    Literal["uniform", "normal", "spike"],
    DEFAULT_CONFIG.numbers.distribution,
)


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


class HeuristicsSchema(BaseModel):
    """Schema describing heuristic mapping configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=DEFAULT_CONFIG.heuristics.enabled,
        description="Toggle automatic heuristic provider mapping on or off.",
    )


class ProviderBundleSchema(BaseModel):
    """Schema describing reusable provider bundle definitions."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        description="Provider type identifier registered in the ProviderRegistry.",
    )
    provider_format: str | None = Field(
        default=None,
        description="Optional provider format key for providers that differentiate formats.",
    )
    provider_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments merged into the provider call when this bundle is used.",
    )


class ProviderDefaultRuleSchema(BaseModel):
    """Schema describing matching rules for provider defaults."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        description="Optional identifier for the rule when defined inside an array of tables.",
    )
    bundle: str = Field(
        description="Name of the bundle applied when the rule matches.",
    )
    summary_types: list[str] = Field(
        default_factory=list,
        description="FieldSummary.type values that must match (e.g., 'string', 'email').",
    )
    formats: list[str] = Field(
        default_factory=list,
        description="Optional FieldSummary.format values that must match (e.g., 'slug').",
    )
    annotation_globs: list[str] = Field(
        default_factory=list,
        description=
        "Glob patterns matched against fully-qualified annotation paths (e.g., 'pydantic.*EmailStr').",
    )
    metadata: list[str] = Field(
        default_factory=list,
        description="Metadata class paths that must all be present (alias for metadata_all).",
    )
    metadata_all: list[str] = Field(
        default_factory=list,
        description="Additional metadata class paths that must all be present.",
    )
    metadata_any: list[str] = Field(
        default_factory=list,
        description="Metadata class paths where at least one must be present.",
    )


class ProviderDefaultsSchema(BaseModel):
    """Schema describing provider default configuration."""

    model_config = ConfigDict(extra="forbid")

    bundles: dict[str, ProviderBundleSchema] = Field(
        default_factory=dict,
        description="Named bundles referencing providers and kwargs that can be reused across rules.",
    )
    rules: list[ProviderDefaultRuleSchema] | dict[str, ProviderDefaultRuleSchema] | None = Field(
        default=None,
        description="List or mapping of rules that map annotations/types onto bundles.",
    )


class PersistenceHandlerSchema(BaseModel):
    """Schema describing a single persistence handler definition."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        description="Dotted path or entry point to the handler callable or class.",
    )
    kind: Literal["sync", "async"] | None = Field(
        default=None,
        description="Override the handler kind when auto-detection is insufficient.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments passed to the handler when instantiated.",
    )


class PersistenceSchema(BaseModel):
    """Schema describing persistence handler configuration."""

    model_config = ConfigDict(extra="forbid")

    handlers: dict[str, PersistenceHandlerSchema] = Field(
        default_factory=dict,
        description="Named handlers referenced by `pfg persist --handler`.",
    )


class FieldHintsSchema(BaseModel):
    """Schema describing default/example preference settings."""

    model_config = ConfigDict(extra="forbid")

    mode: FieldHintModeLiteral = Field(
        default="none",
        description="Global preference for using defaults/examples ('defaults', 'examples', etc.).",
    )
    models: dict[str, FieldHintModeLiteral] = Field(
        default_factory=dict,
        description="Per-model overrides mapping glob patterns to field hint modes.",
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
    profile: str | None = Field(
        default=DEFAULT_CONFIG.profile,
        description="Privacy profile applied ahead of other configuration (e.g., 'pii-safe').",
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
    max_depth: int = Field(
        default=DEFAULT_CONFIG.max_depth,
        ge=1,
        description="Maximum recursion depth before cycle handling policy is applied.",
    )
    cycle_policy: CyclePolicyLiteral = Field(
        default=DEFAULT_CYCLE_POLICY,
        description="How recursive references are resolved (`reuse`, `stub`, or `null`).",
    )
    rng_mode: RngModeLiteral = Field(
        default=DEFAULT_RNG_MODE,
        description=(
            "Random generator mode (`portable` for cross-platform determinism, "
            "`legacy` to use CPython's RNG)."
        ),
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
    forward_refs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of forward reference names to their fully-qualified target types "
            "(e.g., 'app.schemas:Node')."
        ),
    )
    arrays: ArraySettingsSchema = Field(
        default_factory=ArraySettingsSchema,
        description=(
            "Configuration for NumPy array generation: max_ndim, max_side, max_elements, dtypes."
        ),
    )
    heuristics: HeuristicsSchema = Field(
        default_factory=HeuristicsSchema,
        description="Controls the heuristic provider mapping engine.",
    )
    identifiers: IdentifierSettingsSchema = Field(
        default_factory=lambda: IdentifierSettingsSchema(),
        description=(
            "Configuration for identifier providers (secret lengths, URL schemes, UUID version)."
        ),
    )
    numbers: NumbersSettingsSchema = Field(
        default_factory=lambda: NumbersSettingsSchema(),
        description="Control numeric distributions (uniform, normal, spike).",
    )
    paths: PathSettingsSchema = Field(
        default_factory=lambda: PathSettingsSchema(),
        description="Configuration for filesystem path providers.",
    )
    provider_defaults: ProviderDefaultsSchema = Field(
        default_factory=ProviderDefaultsSchema,
        description="Reusable provider bundles plus type/annotation matching rules applied ahead of heuristics.",
    )
    persistence: PersistenceSchema = Field(
        default_factory=PersistenceSchema,
        description="Custom persistence handler definitions referenced by `pfg persist`.",
    )
    field_hints: FieldHintsSchema = Field(
        default_factory=FieldHintsSchema,
        description="Controls when model defaults/examples override provider generation.",
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
    mask_sensitive: bool = Field(
        default=DEFAULT_CONFIG.identifiers.mask_sensitive,
        description="Mask email domains, URLs, cards, and IPs with reserved example data.",
    )


class NumbersSettingsSchema(BaseModel):
    """Schema describing numeric distribution controls."""

    model_config = ConfigDict(extra="forbid")

    distribution: Literal["uniform", "normal", "spike"] = Field(
        default=DEFAULT_NUMBER_DISTRIBUTION,
        description="Distribution applied to ints/floats/decimals.",
    )
    normal_stddev_fraction: float = Field(
        default=DEFAULT_CONFIG.numbers.normal_stddev_fraction,
        gt=0.0,
        description="For normal distribution, standard deviation as a fraction of the value range.",
    )
    spike_ratio: float = Field(
        default=DEFAULT_CONFIG.numbers.spike_ratio,
        ge=0.0,
        le=1.0,
        description="Probability of sampling inside the spike window when distribution='spike'.",
    )
    spike_width_fraction: float = Field(
        default=DEFAULT_CONFIG.numbers.spike_width_fraction,
        gt=0.0,
        description="Spike window width expressed as a fraction of the min/max range.",
    )


class PathSettingsSchema(BaseModel):
    """Schema describing filesystem path provider settings."""

    model_config = ConfigDict(extra="forbid")

    default_os: str = Field(
        default=DEFAULT_CONFIG.paths.default_os,
        description="Default OS target for generated filesystem paths.",
        json_schema_extra={"enum": ["posix", "windows", "mac"]},
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
