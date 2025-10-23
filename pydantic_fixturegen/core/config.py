"""Configuration loader for pydantic-fixturegen."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from importlib import import_module
from pathlib import Path
from typing import Any, TypeVar, cast

from .seed import DEFAULT_LOCALE


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
class AppConfig:
    seed: int | str | None = None
    locale: str = DEFAULT_LOCALE
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    p_none: float | None = None
    union_policy: str = "first"
    enum_policy: str = "first"
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    emitters: EmittersConfig = field(default_factory=EmittersConfig)
    json: JsonConfig = field(default_factory=JsonConfig)


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
    _deep_merge(data, file_config)

    env_config = _load_env_config(env or os.environ)
    _deep_merge(data, env_config)

    if cli:
        _deep_merge(data, cli)

    return _build_app_config(data)


def _config_defaults_dict() -> dict[str, Any]:
    return {
        "seed": DEFAULT_CONFIG.seed,
        "locale": DEFAULT_CONFIG.locale,
        "include": list(DEFAULT_CONFIG.include),
        "exclude": list(DEFAULT_CONFIG.exclude),
        "p_none": DEFAULT_CONFIG.p_none,
        "union_policy": DEFAULT_CONFIG.union_policy,
        "enum_policy": DEFAULT_CONFIG.enum_policy,
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

    overrides_value = _normalize_overrides(data.get("overrides"))

    emitters_value = _normalize_emitters(data.get("emitters"))
    json_value = _normalize_json(data.get("json"))

    seed_value: int | str | None
    if isinstance(seed, (int, str)) or seed is None:
        seed_value = seed
    else:
        raise ConfigError("seed must be an int, str, or null.")

    config = AppConfig(
        seed=seed_value,
        locale=locale,
        include=include,
        exclude=exclude,
        p_none=p_none_value,
        union_policy=union_policy,
        enum_policy=enum_policy,
        overrides=overrides_value,
        emitters=emitters_value,
        json=json_value,
    )

    return config


def _coerce_str(value: Any, field_name: str) -> str:
    if value is None:
        return cast(str, getattr(DEFAULT_CONFIG, field_name))
    if not isinstance(value, str):
        raise ConfigError(f"{field_name} must be a string.")
    return value


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
