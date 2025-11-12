"""Configuration loader for pydantic-fixturegen."""

from __future__ import annotations

import datetime
import fnmatch
import os
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, TypeVar, cast

from faker import Faker

from .field_policies import FieldPolicy
from .presets import get_preset_spec, normalize_preset_name
from .privacy_profiles import get_privacy_profile_spec, normalize_privacy_profile_name
from .seed import DEFAULT_LOCALE, RNGModeLiteral
from .seed_freeze import canonical_module_name


def _import_tomllib() -> Any:
    try:  # pragma: no cover - runtime path
        return import_module("tomllib")
    except ModuleNotFoundError:  # pragma: no cover
        return import_module("tomli")


tomllib = cast(Any, _import_tomllib())

try:  # pragma: no cover - optional dependency
    yaml = cast(Any, import_module("yaml"))
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

_DEFAULT_PYPROJECT = Path("pyproject.toml")
_DEFAULT_YAML_NAMES = (
    Path("pydantic-fixturegen.yaml"),
    Path("pydantic-fixturegen.yml"),
)

UNION_POLICIES = {"first", "random", "weighted"}
ENUM_POLICIES = {"first", "random"}
CYCLE_POLICIES = {"reuse", "stub", "null"}
RNG_MODES = {"portable", "legacy"}
FIELD_HINT_MODES = {
    "none",
    "defaults",
    "examples",
    "defaults-then-examples",
    "examples-then-defaults",
}

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


class ConfigError(ValueError):
    """Raised when configuration sources contain invalid data."""


@dataclass(frozen=True)
class PytestEmitterConfig:
    style: str = "functions"
    scope: str = "function"


@dataclass(frozen=True)
class JsonConfig:
    indent: int = 2
    orjson: bool = False


@dataclass(frozen=True)
class EmittersConfig:
    pytest: PytestEmitterConfig = field(default_factory=PytestEmitterConfig)


@dataclass(frozen=True)
class ArrayConfig:
    max_ndim: int = 2
    max_side: int = 4
    max_elements: int = 16
    dtypes: tuple[str, ...] = ("float64",)


@dataclass(frozen=True)
class IdentifierConfig:
    secret_str_length: int = 16
    secret_bytes_length: int = 16
    url_schemes: tuple[str, ...] = ("https",)
    url_include_path: bool = True
    uuid_version: int = 4
    mask_sensitive: bool = False


@dataclass(frozen=True)
class NumberDistributionConfig:
    distribution: str = "uniform"
    normal_stddev_fraction: float = 0.25
    spike_ratio: float = 0.7
    spike_width_fraction: float = 0.1


@dataclass(frozen=True)
class PathConfig:
    default_os: str = "posix"
    model_targets: tuple[tuple[str, str], ...] = ()

    def target_for(self, model: type[Any] | None) -> str:
        """Return the target OS for the provided model."""

        if model is None or not self.model_targets:
            return self.default_os

        module = canonical_module_name(model)
        qualname = getattr(model, "__qualname__", getattr(model, "__name__", ""))
        full_name = f"{module}.{qualname}" if module else qualname

        for pattern, target in self.model_targets:
            if fnmatch.fnmatchcase(full_name, pattern):
                return target
        return self.default_os


@dataclass(frozen=True)
class RelationLinkConfig:
    source: str
    target: str


@dataclass(frozen=True)
class HeuristicConfig:
    enabled: bool = True


@dataclass(frozen=True)
class PolyfactoryConfig:
    enabled: bool = True
    prefer_delegation: bool = True
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderBundleConfig:
    name: str
    provider: str
    provider_format: str | None = None
    provider_kwargs: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class ProviderDefaultRule:
    name: str
    bundle: str
    summary_types: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    annotation_globs: tuple[str, ...] = ()
    metadata_all: tuple[str, ...] = ()
    metadata_any: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderDefaultsConfig:
    bundles: tuple[ProviderBundleConfig, ...] = ()
    rules: tuple[ProviderDefaultRule, ...] = ()


FieldHintModeLiteral = Literal[
    "none",
    "defaults",
    "examples",
    "defaults-then-examples",
    "examples-then-defaults",
]


@dataclass(frozen=True)
class FieldHintConfig:
    mode: FieldHintModeLiteral = "none"
    model_modes: tuple[tuple[str, FieldHintModeLiteral], ...] = ()


@dataclass(frozen=True)
class AppConfig:
    preset: str | None = None
    profile: str | None = None
    seed: int | str | None = None
    locale: str = DEFAULT_LOCALE
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    p_none: float | None = None
    union_policy: str = "first"
    enum_policy: str = "first"
    max_depth: int = 5
    cycle_policy: str = "reuse"
    rng_mode: RNGModeLiteral = "portable"
    now: datetime.datetime | None = None
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    field_policies: tuple[FieldPolicy, ...] = ()
    locale_policies: tuple[FieldPolicy, ...] = ()
    arrays: ArrayConfig = field(default_factory=ArrayConfig)
    identifiers: IdentifierConfig = field(default_factory=IdentifierConfig)
    numbers: NumberDistributionConfig = field(default_factory=NumberDistributionConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    field_hints: FieldHintConfig = field(default_factory=FieldHintConfig)
    provider_defaults: ProviderDefaultsConfig = field(default_factory=ProviderDefaultsConfig)
    emitters: EmittersConfig = field(default_factory=EmittersConfig)
    json: JsonConfig = field(default_factory=JsonConfig)
    respect_validators: bool = False
    validator_max_retries: int = 2
    relations: tuple[RelationLinkConfig, ...] = ()
    heuristics: HeuristicConfig = field(default_factory=HeuristicConfig)
    polyfactory: PolyfactoryConfig = field(default_factory=PolyfactoryConfig)


DEFAULT_CONFIG = AppConfig()

T = TypeVar("T")


def load_config(
    *,
    root: Path | str | None = None,
    pyproject_path: Path | str | None = None,
    yaml_path: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    cli: Mapping[str, Any] | None = None,
) -> AppConfig:
    """Load configuration applying precedence CLI > env > config > defaults."""
    root_path = Path(root) if root else Path.cwd()
    pyproject = Path(pyproject_path) if pyproject_path else root_path / _DEFAULT_PYPROJECT
    yaml_file = Path(yaml_path) if yaml_path else _find_existing_yaml(root_path)

    data: dict[str, Any] = {}
    _deep_merge(data, _config_defaults_dict())

    file_config = _load_file_config(pyproject, yaml_file)
    _merge_source_with_preset(data, file_config)

    env_config = _load_env_config(env or os.environ)
    _merge_source_with_preset(data, env_config)

    if cli:
        _merge_source_with_preset(data, cli)

    return _build_app_config(data)


def _config_defaults_dict() -> dict[str, Any]:
    return {
        "preset": DEFAULT_CONFIG.preset,
        "profile": DEFAULT_CONFIG.profile,
        "seed": DEFAULT_CONFIG.seed,
        "locale": DEFAULT_CONFIG.locale,
        "include": list(DEFAULT_CONFIG.include),
        "exclude": list(DEFAULT_CONFIG.exclude),
        "p_none": DEFAULT_CONFIG.p_none,
        "union_policy": DEFAULT_CONFIG.union_policy,
        "enum_policy": DEFAULT_CONFIG.enum_policy,
        "max_depth": DEFAULT_CONFIG.max_depth,
        "cycle_policy": DEFAULT_CONFIG.cycle_policy,
        "rng_mode": DEFAULT_CONFIG.rng_mode,
        "now": DEFAULT_CONFIG.now,
        "locales": {},
        "field_policies": {},
        "overrides": {},
        "emitters": {
            "pytest": {
                "style": DEFAULT_CONFIG.emitters.pytest.style,
                "scope": DEFAULT_CONFIG.emitters.pytest.scope,
            }
        },
        "json": {
            "indent": DEFAULT_CONFIG.json.indent,
            "orjson": DEFAULT_CONFIG.json.orjson,
        },
        "arrays": {
            "max_ndim": DEFAULT_CONFIG.arrays.max_ndim,
            "max_side": DEFAULT_CONFIG.arrays.max_side,
            "max_elements": DEFAULT_CONFIG.arrays.max_elements,
            "dtypes": list(DEFAULT_CONFIG.arrays.dtypes),
        },
        "identifiers": {
            "secret_str_length": DEFAULT_CONFIG.identifiers.secret_str_length,
            "secret_bytes_length": DEFAULT_CONFIG.identifiers.secret_bytes_length,
            "url_schemes": list(DEFAULT_CONFIG.identifiers.url_schemes),
            "url_include_path": DEFAULT_CONFIG.identifiers.url_include_path,
            "uuid_version": DEFAULT_CONFIG.identifiers.uuid_version,
            "mask_sensitive": DEFAULT_CONFIG.identifiers.mask_sensitive,
        },
        "provider_defaults": {
            "bundles": {},
            "rules": [],
        },
        "numbers": {
            "distribution": DEFAULT_CONFIG.numbers.distribution,
            "normal_stddev_fraction": DEFAULT_CONFIG.numbers.normal_stddev_fraction,
            "spike_ratio": DEFAULT_CONFIG.numbers.spike_ratio,
            "spike_width_fraction": DEFAULT_CONFIG.numbers.spike_width_fraction,
        },
        "paths": {
            "default_os": DEFAULT_CONFIG.paths.default_os,
            "models": {pattern: target for pattern, target in DEFAULT_CONFIG.paths.model_targets},
        },
        "field_hints": {
            "mode": DEFAULT_CONFIG.field_hints.mode,
            "models": {},
        },
        "polyfactory": {
            "enabled": DEFAULT_CONFIG.polyfactory.enabled,
            "prefer_delegation": DEFAULT_CONFIG.polyfactory.prefer_delegation,
            "modules": list(DEFAULT_CONFIG.polyfactory.modules),
        },
        "respect_validators": DEFAULT_CONFIG.respect_validators,
        "validator_max_retries": DEFAULT_CONFIG.validator_max_retries,
        "relations": {},
        "heuristics": {
            "enabled": DEFAULT_CONFIG.heuristics.enabled,
        },
    }


def _load_file_config(pyproject_path: Path, yaml_path: Path | None) -> dict[str, Any]:
    config: dict[str, Any] = {}

    if pyproject_path.is_file():
        with pyproject_path.open("rb") as fh:
            pyproject_data = tomllib.load(fh)
        tool_config = cast(Mapping[str, Any], pyproject_data.get("tool", {}))
        project_config = cast(Mapping[str, Any], tool_config.get("pydantic_fixturegen", {}))
        config = _ensure_mutable(project_config)

    if yaml_path and yaml_path.is_file():
        if yaml is None:
            raise ConfigError("YAML configuration provided but PyYAML is not installed.")
        with yaml_path.open("r", encoding="utf-8") as fh:
            yaml_data = yaml.safe_load(fh) or {}
        if not isinstance(yaml_data, Mapping):
            raise ConfigError("YAML configuration must be a mapping at the top level.")
        yaml_dict = _ensure_mutable(yaml_data)
        _deep_merge(config, yaml_dict)

    return config


def _find_existing_yaml(root: Path) -> Path | None:
    for candidate in _DEFAULT_YAML_NAMES:
        path = root / candidate
        if path.is_file():
            return path
    return None


def _load_env_config(env: Mapping[str, str]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    prefix = "PFG_"

    for key, raw_value in env.items():
        if not key.startswith(prefix):
            continue
        path_segments = key[len(prefix) :].split("__")
        if not path_segments:
            continue

        top_key = path_segments[0].lower()
        nested_segments = path_segments[1:]

        target = cast(MutableMapping[str, Any], config)
        current_key = top_key
        preserve_case = top_key == "overrides"

        for index, segment in enumerate(nested_segments):
            next_key = segment if preserve_case else segment.lower()

            if index == len(nested_segments) - 1:
                value = _coerce_env_value(raw_value)
                _set_nested_value(target, current_key, next_key, value)
            else:
                next_container = cast(MutableMapping[str, Any], target.setdefault(current_key, {}))
                target = next_container
                current_key = next_key
                preserve_case = preserve_case or current_key == "overrides"

        if not nested_segments:
            value = _coerce_env_value(raw_value)
            target[current_key] = value

    return config


def _set_nested_value(
    mapping: MutableMapping[str, Any], current_key: str, next_key: str, value: Any
) -> None:
    if current_key not in mapping or not isinstance(mapping[current_key], MutableMapping):
        mapping[current_key] = {}
    nested = cast(MutableMapping[str, Any], mapping[current_key])
    nested[next_key] = value


def _coerce_env_value(value: str) -> Any:
    stripped = value.strip()
    lower = stripped.lower()

    if lower in TRUTHY:
        return True
    if lower in FALSY:
        return False

    if "," in stripped:
        return [part.strip() for part in stripped.split(",") if part.strip()]

    try:
        return int(stripped)
    except ValueError:
        pass

    try:
        return float(stripped)
    except ValueError:
        pass

    return stripped


def _build_app_config(data: Mapping[str, Any]) -> AppConfig:
    preset_value = _coerce_preset_value(data.get("preset"))
    profile_value = _coerce_profile_value(data.get("profile"))

    seed = data.get("seed")
    locale = _coerce_str(data.get("locale"), "locale")
    include = _normalize_sequence(data.get("include"))
    exclude = _normalize_sequence(data.get("exclude"))

    p_none = data.get("p_none")
    if p_none is not None:
        try:
            p_val = float(p_none)
        except (TypeError, ValueError) as exc:
            raise ConfigError("p_none must be a float value.") from exc
        if not (0.0 <= p_val <= 1.0):
            raise ConfigError("p_none must be between 0.0 and 1.0 inclusive.")
        p_none_value: float | None = p_val
    else:
        p_none_value = None

    union_policy = _coerce_policy(data.get("union_policy"), UNION_POLICIES, "union_policy")
    enum_policy = _coerce_policy(data.get("enum_policy"), ENUM_POLICIES, "enum_policy")
    max_depth_value = _coerce_positive_int(
        data.get("max_depth"),
        field_name="max_depth",
        default=DEFAULT_CONFIG.max_depth,
    )
    cycle_policy_value = _coerce_cycle_policy(
        data.get("cycle_policy"),
        field_name="cycle_policy",
    )
    rng_mode_value: RNGModeLiteral = _coerce_rng_mode(data.get("rng_mode"))

    overrides_value = _normalize_overrides(data.get("overrides"))

    emitters_value = _normalize_emitters(data.get("emitters"))
    json_value = _normalize_json(data.get("json"))
    field_policies_value = _normalize_field_policies(data.get("field_policies"))
    locale_policies_value = _normalize_locale_policies(data.get("locales"))
    arrays_value = _normalize_array_config(data.get("arrays"))
    identifiers_value = _normalize_identifier_config(data.get("identifiers"))
    field_hints_value = _normalize_field_hints(data.get("field_hints"))
    provider_defaults_value = _normalize_provider_defaults(data.get("provider_defaults"))
    numbers_value = _normalize_number_config(data.get("numbers"))
    paths_value = _normalize_path_config(data.get("paths"))
    relations_value = _normalize_relations(data.get("relations"))
    heuristics_value = _normalize_heuristics(data.get("heuristics"))
    polyfactory_value = _normalize_polyfactory_config(data.get("polyfactory"))
    now_value = _coerce_datetime(data.get("now"), "now")

    seed_value: int | str | None
    if isinstance(seed, int | str) or seed is None:
        seed_value = seed
    else:
        raise ConfigError("seed must be an int, str, or null.")

    respect_validators_value = _coerce_bool_value(
        data.get("respect_validators"),
        field_name="respect_validators",
        default=DEFAULT_CONFIG.respect_validators,
    )
    validator_max_retries_value = _coerce_non_negative_int(
        data.get("validator_max_retries"),
        field_name="validator_max_retries",
        default=DEFAULT_CONFIG.validator_max_retries,
    )

    config = AppConfig(
        preset=preset_value,
        profile=profile_value,
        seed=seed_value,
        locale=locale,
        include=include,
        exclude=exclude,
        p_none=p_none_value,
        union_policy=union_policy,
        enum_policy=enum_policy,
        now=now_value,
        overrides=overrides_value,
        field_policies=field_policies_value,
        locale_policies=locale_policies_value,
        arrays=arrays_value,
        identifiers=identifiers_value,
        field_hints=field_hints_value,
        provider_defaults=provider_defaults_value,
        numbers=numbers_value,
        paths=paths_value,
        emitters=emitters_value,
        json=json_value,
        respect_validators=respect_validators_value,
        validator_max_retries=validator_max_retries_value,
        relations=relations_value,
        max_depth=max_depth_value,
        cycle_policy=cycle_policy_value,
        rng_mode=rng_mode_value,
        heuristics=heuristics_value,
        polyfactory=polyfactory_value,
    )

    return config


def _coerce_str(value: Any, field_name: str) -> str:
    if value is None:
        return cast(str, getattr(DEFAULT_CONFIG, field_name))
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    return value


def _coerce_bool_value(value: Any, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUTHY:
            return True
        if lowered in FALSY:
            return False
    raise ConfigError(f"{field_name} must be a boolean value.")


def _coerce_non_negative_int(value: Any, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigError(f"{field_name} must be a non-negative integer.")
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} must be a non-negative integer.") from exc
    if coerced < 0:
        raise ConfigError(f"{field_name} must be >= 0.")
    return coerced


def _coerce_positive_int(value: Any, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigError(f"{field_name} must be a positive integer.")
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} must be a positive integer.") from exc
    if coerced <= 0:
        raise ConfigError(f"{field_name} must be > 0.")
    return coerced


def _coerce_cycle_policy(value: Any, *, field_name: str) -> str:
    default = DEFAULT_CONFIG.cycle_policy
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    lowered = value.strip().lower()
    if lowered not in CYCLE_POLICIES:
        raise ConfigError(f"{field_name} must be one of {sorted(CYCLE_POLICIES)}.")
    return lowered


def _coerce_rng_mode(value: Any) -> RNGModeLiteral:
    default = DEFAULT_CONFIG.rng_mode
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError("rng_mode must be a string.")
    lowered = value.strip().lower()
    if lowered not in RNG_MODES:
        raise ConfigError(f"rng_mode must be one of {sorted(RNG_MODES)}.")
    return cast(RNGModeLiteral, lowered)


def _normalize_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return tuple(parts)
    if isinstance(value, Sequence):
        sequence_items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ConfigError("Sequence values must contain only strings.")
            sequence_items.append(item)
        return tuple(sequence_items)
    raise ConfigError("Expected a sequence or string value.")


def _coerce_policy(value: Any, allowed: set[str], field_name: str) -> str:
    default_value = cast(str, getattr(DEFAULT_CONFIG, field_name))
    if value is None:
        return default_value
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    if value not in allowed:
        raise ConfigError(f"{field_name} must be one of {sorted(allowed)}.")
    return value


def _coerce_field_hint_mode(value: Any, label: str) -> FieldHintModeLiteral:
    if value is None:
        return DEFAULT_CONFIG.field_hints.mode
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be one of {sorted(FIELD_HINT_MODES)}.")
    lowered = value.strip().lower()
    if lowered not in FIELD_HINT_MODES:
        raise ConfigError(f"{label} must be one of {sorted(FIELD_HINT_MODES)}.")
    return cast(FieldHintModeLiteral, lowered)


def _coerce_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} must be a mapping.")
    frozen: dict[str, Any] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise ConfigError(f"{label} keys must be non-empty strings.")
        frozen[key] = entry
    return MappingProxyType(frozen)


def _coerce_str_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ConfigError(f"{label} entries must be non-empty strings.")
        return (text,)
    if isinstance(value, Sequence):
        results: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise ConfigError(f"{label} entries must be strings.")
            text = entry.strip()
            if not text:
                raise ConfigError(f"{label} entries must be non-empty strings.")
            results.append(text)
        return tuple(results)
    raise ConfigError(f"{label} must be a string or list of strings.")


def _coerce_datetime(value: Any, field_name: str) -> datetime.datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time(), tzinfo=datetime.timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "none":
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ConfigError(f"{field_name} must be an ISO 8601 datetime string.") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    raise ConfigError(f"{field_name} must be an ISO 8601 datetime string or datetime object.")


def _normalize_overrides(value: Any) -> Mapping[str, Mapping[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError("overrides must be a mapping.")

    overrides: dict[str, dict[str, Any]] = {}
    for model_key, fields in value.items():
        if not isinstance(model_key, str):
            raise ConfigError("override model keys must be strings.")
        if not isinstance(fields, Mapping):
            raise ConfigError("override fields must be mappings.")
        overrides[model_key] = {}
        for field_name, field_config in fields.items():
            if not isinstance(field_name, str):
                raise ConfigError("override field names must be strings.")
            overrides[model_key][field_name] = field_config
    return overrides


def _normalize_field_policies(value: Any) -> tuple[FieldPolicy, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ConfigError("field_policies must be a mapping of pattern to policy settings.")

    policies: list[FieldPolicy] = []
    for index, (pattern, raw_options) in enumerate(value.items()):
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigError("field policy keys must be non-empty strings.")
        if not isinstance(raw_options, Mapping):
            raise ConfigError(f"Field policy '{pattern}' must be a mapping of options.")

        p_none = raw_options.get("p_none")
        if p_none is not None:
            try:
                p_none = float(p_none)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"Field policy '{pattern}' p_none must be a float value."
                ) from exc
            if not (0.0 <= p_none <= 1.0):
                raise ConfigError(f"Field policy '{pattern}' p_none must be between 0.0 and 1.0.")

        enum_policy = raw_options.get("enum_policy")
        if enum_policy is not None and (
            not isinstance(enum_policy, str) or enum_policy not in ENUM_POLICIES
        ):
            raise ConfigError(
                f"Field policy '{pattern}' enum_policy must be one of {sorted(ENUM_POLICIES)}."
            )

        union_policy = raw_options.get("union_policy")
        if union_policy is not None and (
            not isinstance(union_policy, str) or union_policy not in UNION_POLICIES
        ):
            raise ConfigError(
                f"Field policy '{pattern}' union_policy must be one of {sorted(UNION_POLICIES)}."
            )

        allowed_keys = {"p_none", "enum_policy", "union_policy"}
        for option_key in raw_options:
            if option_key not in allowed_keys:
                raise ConfigError(
                    f"Field policy '{pattern}' contains unsupported option '{option_key}'."
                )

        options = {"p_none": p_none, "enum_policy": enum_policy, "union_policy": union_policy}
        policies.append(FieldPolicy(pattern=pattern, options=options, index=index))

    return tuple(policies)


def _normalize_locale_policies(value: Any) -> tuple[FieldPolicy, ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ConfigError("locales must be a mapping of pattern to locale strings.")

    policies: list[FieldPolicy] = []
    for index, (pattern, raw_locale) in enumerate(value.items()):
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigError("Locale mapping keys must be non-empty strings.")
        if not isinstance(raw_locale, str) or not raw_locale.strip():
            raise ConfigError(f"Locale mapping '{pattern}' must specify a non-empty string value.")

        locale_value = raw_locale.strip()
        try:
            Faker(locale_value)
        except Exception as exc:  # pragma: no cover - defensive against Faker internals
            raise ConfigError(
                f"Locale mapping '{pattern}' references unsupported locale '{locale_value}'."
            ) from exc

        policies.append(FieldPolicy(pattern=pattern, options={"locale": locale_value}, index=index))

    return tuple(policies)


def _normalize_emitters(value: Any) -> EmittersConfig:
    pytest_config = PytestEmitterConfig()

    if value:
        if not isinstance(value, Mapping):
            raise ConfigError("emitters must be a mapping.")
        pytest_data = value.get("pytest")
        if pytest_data is not None:
            if not isinstance(pytest_data, Mapping):
                raise ConfigError("emitters.pytest must be a mapping.")
            pytest_config = replace(
                pytest_config,
                style=_coerce_optional_str(pytest_data.get("style"), "emitters.pytest.style"),
                scope=_coerce_optional_str(pytest_data.get("scope"), "emitters.pytest.scope"),
            )

    return EmittersConfig(pytest=pytest_config)


def _normalize_json(value: Any) -> JsonConfig:
    json_config = JsonConfig()

    if value is None:
        return json_config
    if not isinstance(value, Mapping):
        raise ConfigError("json configuration must be a mapping.")

    indent_raw = value.get("indent", json_config.indent)
    orjson_raw = value.get("orjson", json_config.orjson)

    indent = _coerce_indent(indent_raw)
    orjson = _coerce_bool(orjson_raw, "json.orjson")

    return JsonConfig(indent=indent, orjson=orjson)


def _normalize_array_config(value: Any) -> ArrayConfig:
    config = ArrayConfig()
    if value is None:
        return config
    if not isinstance(value, Mapping):
        raise ConfigError("arrays configuration must be a mapping.")

    max_ndim_raw = value.get("max_ndim", config.max_ndim)
    max_side_raw = value.get("max_side", config.max_side)
    max_elements_raw = value.get("max_elements", config.max_elements)
    dtypes_raw = value.get("dtypes", config.dtypes)

    try:
        max_ndim = int(max_ndim_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("arrays.max_ndim must be an integer.") from exc
    if max_ndim <= 0:
        raise ConfigError("arrays.max_ndim must be >= 1.")

    try:
        max_side = int(max_side_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("arrays.max_side must be an integer.") from exc
    if max_side <= 0:
        raise ConfigError("arrays.max_side must be >= 1.")

    try:
        max_elements = int(max_elements_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("arrays.max_elements must be an integer.") from exc
    if max_elements <= 0:
        raise ConfigError("arrays.max_elements must be >= 1.")

    if isinstance(dtypes_raw, str):
        dtype_values = tuple(val.strip() for val in dtypes_raw.split(",") if val.strip())
    elif isinstance(dtypes_raw, Sequence):
        dtype_buffer: list[str] = []
        for item in dtypes_raw:
            if not isinstance(item, str) or not item.strip():
                raise ConfigError("arrays.dtypes entries must be non-empty strings.")
            dtype_buffer.append(item.strip())
        dtype_values = tuple(dtype_buffer)
    else:
        raise ConfigError("arrays.dtypes must be a list or comma-separated string.")

    if not dtype_values:
        raise ConfigError("arrays.dtypes must contain at least one dtype string.")

    return ArrayConfig(
        max_ndim=max_ndim,
        max_side=max_side,
        max_elements=max_elements,
        dtypes=dtype_values,
    )


def _normalize_identifier_config(value: Any) -> IdentifierConfig:
    config = IdentifierConfig()
    if value is None:
        return config
    if not isinstance(value, Mapping):
        raise ConfigError("identifiers configuration must be a mapping.")

    secret_str_raw = value.get("secret_str_length", config.secret_str_length)
    secret_bytes_raw = value.get("secret_bytes_length", config.secret_bytes_length)
    url_schemes_raw = value.get("url_schemes", config.url_schemes)
    url_include_path_raw = value.get("url_include_path", config.url_include_path)
    uuid_version_raw = value.get("uuid_version", config.uuid_version)
    mask_sensitive_raw = value.get("mask_sensitive", config.mask_sensitive)

    try:
        secret_str_length = int(secret_str_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("identifiers.secret_str_length must be an integer.") from exc
    if secret_str_length <= 0:
        raise ConfigError("identifiers.secret_str_length must be >= 1.")

    try:
        secret_bytes_length = int(secret_bytes_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("identifiers.secret_bytes_length must be an integer.") from exc
    if secret_bytes_length <= 0:
        raise ConfigError("identifiers.secret_bytes_length must be >= 1.")

    if isinstance(url_schemes_raw, str):
        schemes = tuple(s.strip() for s in url_schemes_raw.split(",") if s.strip())
    elif isinstance(url_schemes_raw, Sequence):
        scheme_buffer: list[str] = []
        for item in url_schemes_raw:
            if not isinstance(item, str) or not item.strip():
                raise ConfigError("identifiers.url_schemes entries must be non-empty strings.")
            scheme_buffer.append(item.strip())
        schemes = tuple(scheme_buffer)
    else:
        raise ConfigError("identifiers.url_schemes must be a list or comma-separated string.")

    if not schemes:
        raise ConfigError("identifiers.url_schemes must contain at least one scheme string.")

    if not isinstance(url_include_path_raw, bool):
        raise ConfigError("identifiers.url_include_path must be a boolean.")
    url_include_path = url_include_path_raw

    try:
        uuid_version = int(uuid_version_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("identifiers.uuid_version must be an integer.") from exc
    if uuid_version not in {1, 4}:
        raise ConfigError("identifiers.uuid_version must be 1 or 4.")

    if not isinstance(mask_sensitive_raw, bool):
        raise ConfigError("identifiers.mask_sensitive must be a boolean.")

    return IdentifierConfig(
        secret_str_length=secret_str_length,
        secret_bytes_length=secret_bytes_length,
        url_schemes=schemes,
        url_include_path=url_include_path,
        uuid_version=uuid_version,
        mask_sensitive=mask_sensitive_raw,
    )


def _normalize_field_hints(value: Any) -> FieldHintConfig:
    if value is None:
        return FieldHintConfig()
    if not isinstance(value, Mapping):
        raise ConfigError("field_hints must be a mapping.")

    mode = _coerce_field_hint_mode(value.get("mode"), "field_hints.mode")

    models_raw = value.get("models")
    model_modes: list[tuple[str, FieldHintModeLiteral]] = []
    if models_raw is not None:
        if not isinstance(models_raw, Mapping):
            raise ConfigError("field_hints.models must be a mapping of pattern to mode.")
        for pattern, entry in models_raw.items():
            if not isinstance(pattern, str) or not pattern.strip():
                raise ConfigError("field_hints model patterns must be non-empty strings.")
            pattern_mode = _coerce_field_hint_mode(
                entry,
                f"field_hints.models['{pattern}']",
            )
            model_modes.append((pattern.strip(), pattern_mode))

    return FieldHintConfig(mode=mode, model_modes=tuple(model_modes))


def _normalize_provider_defaults(value: Any) -> ProviderDefaultsConfig:
    if value is None:
        return ProviderDefaultsConfig()
    if not isinstance(value, Mapping):
        raise ConfigError("provider_defaults must be a mapping.")

    bundles_raw = value.get("bundles") or {}
    if not isinstance(bundles_raw, Mapping):
        raise ConfigError("provider_defaults.bundles must be a mapping of names to settings.")
    bundles: list[ProviderBundleConfig] = []
    for name, bundle_config in bundles_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("provider bundle names must be non-empty strings.")
        if not isinstance(bundle_config, Mapping):
            raise ConfigError(
                f"provider_defaults.bundles['{name}'] must be a mapping of options."
            )
        provider = bundle_config.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            raise ConfigError(f"provider_defaults.bundles['{name}'].provider must be a string.")
        format_value = bundle_config.get("provider_format", bundle_config.get("format"))
        provider_format: str | None
        if format_value is None:
            provider_format = None
        elif isinstance(format_value, str) and format_value.strip():
            provider_format = format_value.strip()
        else:
            raise ConfigError(
                f"provider_defaults.bundles['{name}'].provider_format must be a string when set."
            )
        kwargs = _coerce_mapping(
            bundle_config.get("provider_kwargs"),
            f"provider_defaults.bundles['{name}'].provider_kwargs",
        )
        bundles.append(
            ProviderBundleConfig(
                name=name.strip(),
                provider=provider.strip(),
                provider_format=provider_format,
                provider_kwargs=kwargs,
            )
        )

    rules_raw = value.get("rules")
    rules: list[ProviderDefaultRule] = []
    if rules_raw is None:
        pass
    elif isinstance(rules_raw, Mapping):
        for rule_name, rule_config in rules_raw.items():
            rules.append(
                _build_provider_rule(
                    rule_config,
                    rule_name if isinstance(rule_name, str) else str(rule_name),
                )
            )
    elif isinstance(rules_raw, (list, tuple)):
        for index, entry in enumerate(rules_raw):
            if isinstance(entry, Mapping):
                declared_name = entry.get("name")
                rule_name = declared_name if isinstance(declared_name, str) else None
            else:
                rule_name = None
            rules.append(_build_provider_rule(entry, rule_name or f"rule_{index}"))
    else:
        raise ConfigError("provider_defaults.rules must be an array or mapping of rule entries.")

    bundle_names = {bundle.name for bundle in bundles}
    for rule in rules:
        if rule.bundle not in bundle_names:
            raise ConfigError(
                f"provider_defaults.rules '{rule.name}' references unknown bundle '{rule.bundle}'."
            )

    return ProviderDefaultsConfig(bundles=tuple(bundles), rules=tuple(rules))


def _build_provider_rule(value: Any, name: str | None) -> ProviderDefaultRule:
    if not isinstance(value, Mapping):
        raise ConfigError("provider_defaults.rules entries must be mappings.")
    label = name or value.get("name") or "unnamed"
    bundle = value.get("bundle")
    if not isinstance(bundle, str) or not bundle.strip():
        raise ConfigError(f"provider_defaults.rules '{label}' must specify a bundle name.")

    summary_types = _coerce_str_tuple(
        value.get("summary_types"),
        f"provider_defaults.rules['{label}'].summary_types",
    )
    formats = _coerce_str_tuple(
        value.get("formats"),
        f"provider_defaults.rules['{label}'].formats",
    )
    annotation_globs = _coerce_str_tuple(
        value.get("annotation_globs"),
        f"provider_defaults.rules['{label}'].annotation_globs",
    )
    metadata_all = _coerce_str_tuple(
        value.get("metadata"),
        f"provider_defaults.rules['{label}'].metadata",
    ) or _coerce_str_tuple(
        value.get("metadata_all"),
        f"provider_defaults.rules['{label}'].metadata_all",
    )
    metadata_any = _coerce_str_tuple(
        value.get("metadata_any"),
        f"provider_defaults.rules['{label}'].metadata_any",
    )

    rule_name = label if isinstance(label, str) else str(label)
    return ProviderDefaultRule(
        name=rule_name,
        bundle=bundle.strip(),
        summary_types=summary_types,
        formats=formats,
        annotation_globs=annotation_globs,
        metadata_all=metadata_all,
        metadata_any=metadata_any,
    )


def _normalize_number_config(value: Any) -> NumberDistributionConfig:
    config = NumberDistributionConfig()
    if value is None:
        return config
    if not isinstance(value, Mapping):
        raise ConfigError("numbers configuration must be a mapping.")

    distribution_raw = value.get("distribution", config.distribution)
    stddev_raw = value.get("normal_stddev_fraction", config.normal_stddev_fraction)
    spike_ratio_raw = value.get("spike_ratio", config.spike_ratio)
    spike_width_raw = value.get("spike_width_fraction", config.spike_width_fraction)

    if not isinstance(distribution_raw, str):
        raise ConfigError("numbers.distribution must be a string.")
    distribution = distribution_raw.strip().lower()
    if distribution not in {"uniform", "normal", "spike"}:
        raise ConfigError("numbers.distribution must be one of 'uniform', 'normal', or 'spike'.")

    try:
        stddev_value = float(stddev_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("numbers.normal_stddev_fraction must be a float.") from exc
    if stddev_value <= 0:
        raise ConfigError("numbers.normal_stddev_fraction must be greater than 0.")

    try:
        spike_ratio_value = float(spike_ratio_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("numbers.spike_ratio must be a float.") from exc
    if not (0.0 <= spike_ratio_value <= 1.0):
        raise ConfigError("numbers.spike_ratio must be between 0.0 and 1.0.")

    try:
        spike_width_value = float(spike_width_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("numbers.spike_width_fraction must be a float.") from exc
    if spike_width_value <= 0:
        raise ConfigError("numbers.spike_width_fraction must be greater than 0.")

    return NumberDistributionConfig(
        distribution=distribution,
        normal_stddev_fraction=stddev_value,
        spike_ratio=spike_ratio_value,
        spike_width_fraction=spike_width_value,
    )


def _normalize_path_config(value: Any) -> PathConfig:
    config = PathConfig()
    if value is None:
        return config
    if not isinstance(value, Mapping):
        raise ConfigError("paths configuration must be a mapping.")

    default_os_raw = value.get("default_os", config.default_os)
    default_os = _coerce_path_target(default_os_raw, "paths.default_os")

    models_raw = value.get("models", value.get("model_targets", ()))
    model_targets: list[tuple[str, str]] = []
    if models_raw:
        if isinstance(models_raw, Mapping):
            for pattern, target in models_raw.items():
                if not isinstance(pattern, str) or not pattern.strip():
                    raise ConfigError("paths.models keys must be non-empty strings.")
                if not isinstance(target, str):
                    raise ConfigError("paths.models values must be strings.")
                normalized = _coerce_path_target(target, f"paths.models['{pattern}']")
                model_targets.append((pattern.strip(), normalized))
        else:
            raise ConfigError("paths.models must be a mapping of pattern to target OS.")

    return PathConfig(default_os=default_os, model_targets=tuple(model_targets))


def _normalize_polyfactory_config(value: Any) -> PolyfactoryConfig:
    if value is None:
        return PolyfactoryConfig()
    if not isinstance(value, Mapping):
        raise ConfigError("polyfactory must be a mapping.")

    enabled = _coerce_bool_value(
        value.get("enabled"),
        field_name="polyfactory.enabled",
        default=DEFAULT_CONFIG.polyfactory.enabled,
    )
    prefer_delegation = _coerce_bool_value(
        value.get("prefer_delegation"),
        field_name="polyfactory.prefer_delegation",
        default=DEFAULT_CONFIG.polyfactory.prefer_delegation,
    )
    modules_raw = value.get("modules")
    modules = _normalize_sequence(modules_raw)
    return PolyfactoryConfig(
        enabled=enabled,
        prefer_delegation=prefer_delegation,
        modules=modules,
    )


def _normalize_relations(value: Any) -> tuple[RelationLinkConfig, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        links: list[RelationLinkConfig] = []
        for source, target in value.items():
            if not isinstance(source, str) or not isinstance(target, str):
                raise ConfigError(
                    "relations must map 'Model.field' strings to 'Model.field' targets."
                )
            links.append(RelationLinkConfig(source=source.strip(), target=target.strip()))
        return tuple(links)
    if isinstance(value, Sequence):
        string_links: list[RelationLinkConfig] = []
        for entry in value:
            if not isinstance(entry, str):
                raise ConfigError("relations entries must be strings formatted as 'source=target'.")
            if "=" not in entry:
                raise ConfigError("relations entries must include '=' between source and target.")
            source_text, target_text = entry.split("=", 1)
            string_links.append(
                RelationLinkConfig(source=source_text.strip(), target=target_text.strip())
            )
        return tuple(string_links)
    raise ConfigError("relations must be provided as a mapping or list of strings.")


def _normalize_heuristics(value: Any) -> HeuristicConfig:
    if value is None:
        return HeuristicConfig()
    if isinstance(value, HeuristicConfig):
        return value
    if not isinstance(value, Mapping):
        raise ConfigError("heuristics must be a mapping.")
    enabled = _coerce_bool_value(
        value.get("enabled"),
        field_name="heuristics.enabled",
        default=DEFAULT_CONFIG.heuristics.enabled,
    )
    return HeuristicConfig(enabled=enabled)


def _coerce_path_target(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    normalized = value.strip().lower()
    if normalized in {"posix", "linux", "unix"}:
        return "posix"
    if normalized in {"windows", "win", "win32"}:
        return "windows"
    if normalized in {"mac", "macos", "darwin"}:
        return "mac"
    raise ConfigError(f"{field_name} must be one of 'posix', 'windows', or 'mac'.")


def _coerce_indent(value: Any) -> int:
    if value is None:
        return JsonConfig().indent
    try:
        indent_val = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("json.indent must be an integer.") from exc
    if indent_val < 0:
        raise ConfigError("json.indent must be non-negative.")
    return indent_val


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.lower()
        if lower in TRUTHY:
            return True
        if lower in FALSY:
            return False
        raise ConfigError(f"{field_name} must be a boolean string.")
    if value is None:
        attr = field_name.split(".")[-1]
        return cast(bool, getattr(DEFAULT_CONFIG.json, attr))
    raise ConfigError(f"{field_name} must be a boolean.")


def _coerce_optional_str(value: Any, field_name: str) -> str:
    if value is None:
        default = DEFAULT_CONFIG.emitters.pytest
        attr = field_name.split(".")[-1]
        return cast(str, getattr(default, attr))
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    return value


def _coerce_preset_value(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("preset must be a string when specified.")
    stripped = value.strip()
    if not stripped:
        return None
    normalized = normalize_preset_name(stripped)
    try:
        spec = get_preset_spec(normalized)
    except KeyError as exc:
        raise ConfigError(f"Unknown preset '{value}'.") from exc
    return spec.name


def _coerce_profile_value(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("profile must be a string when specified.")
    stripped = value.strip()
    if not stripped:
        return None
    normalized = normalize_privacy_profile_name(stripped)
    try:
        spec = get_privacy_profile_spec(normalized)
    except KeyError as exc:
        raise ConfigError(f"Unknown profile '{value}'.") from exc
    return spec.name


def _ensure_mutable(mapping: Mapping[str, Any]) -> dict[str, Any]:
    mutable: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            mutable[key] = _ensure_mutable(value)
        elif isinstance(value, list):
            items: list[Any] = []
            for item in value:
                if isinstance(item, Mapping):
                    items.append(_ensure_mutable(item))
                else:
                    items.append(item)
            mutable[key] = items
        else:
            mutable[key] = value
    return mutable


def _deep_merge(target: MutableMapping[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key in target and isinstance(target[key], MutableMapping) and isinstance(value, Mapping):
            _deep_merge(cast(MutableMapping[str, Any], target[key]), value)
        else:
            if isinstance(value, Mapping):
                target[key] = _ensure_mutable(value)
            elif isinstance(value, list):
                target[key] = list(value)
            else:
                target[key] = value


def _merge_source_with_preset(data: MutableMapping[str, Any], source: Mapping[str, Any]) -> None:
    if not source:
        return

    mutable = _ensure_mutable(source)
    bundles: tuple[tuple[str, Callable[[str], str], Callable[[str], Any]], ...] = (
        ("preset", normalize_preset_name, get_preset_spec),
        ("profile", normalize_privacy_profile_name, get_privacy_profile_spec),
    )

    for key_name, normalizer, resolver in bundles:
        if key_name not in mutable:
            continue
        raw_value = mutable.pop(key_name)
        if raw_value is None:
            data[key_name] = None
            continue
        if not isinstance(raw_value, str):
            raise ConfigError(f"{key_name} must be a string when specified.")
        stripped = raw_value.strip()
        if not stripped:
            data[key_name] = None
            continue
        normalized = normalizer(stripped)
        try:
            spec = resolver(normalized)
        except KeyError as exc:
            raise ConfigError(f"Unknown {key_name} '{raw_value}'.") from exc
        _deep_merge(data, _ensure_mutable(spec.settings))
        data[key_name] = spec.name

    _deep_merge(data, mutable)
