from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_fixturegen.core import config as config_mod
from pydantic_fixturegen.core.config import (
    AppConfig,
    ConfigError,
    JsonConfig,
    PathConfig,
    PytestEmitterConfig,
    load_config,
)
from pydantic_fixturegen.core.seed import DEFAULT_LOCALE

HAS_YAML = config_mod.yaml is not None


def test_default_configuration(tmp_path: Path) -> None:
    config = load_config(root=tmp_path)

    assert isinstance(config, AppConfig)
    assert config.locale == DEFAULT_LOCALE
    assert config.include == ()
    assert config.emitters.pytest == PytestEmitterConfig()
    assert config.json == JsonConfig()
    assert config.field_policies == ()
    assert config.locale_policies == ()
    assert config.now is None
    assert config.paths == PathConfig()


def test_load_from_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
        [tool.pydantic_fixturegen]
        seed = 123
        locale = "sv_SE"
        include = ["app.models.*"]
        exclude = ["tests.*", "internal.*"]
        p_none = 0.25
        union_policy = "weighted"
        enum_policy = "random"

        [tool.pydantic_fixturegen.emitters.pytest]
        style = "factory"
        scope = "module"

        [tool.pydantic_fixturegen.json]
        indent = 0
        orjson = true

        [tool.pydantic_fixturegen.overrides."app.models.User".email]
        provider = "email"

        [tool.pydantic_fixturegen.paths]
        default_os = "windows"
        models = {"app.models.*" = "mac"}
        """,
        encoding="utf-8",
    )

    config = load_config(root=tmp_path)

    assert config.seed == 123
    assert config.locale == "sv_SE"
    assert config.include == ("app.models.*",)
    assert config.exclude == ("tests.*", "internal.*")
    assert config.p_none == pytest.approx(0.25)
    assert config.union_policy == "weighted"
    assert config.enum_policy == "random"
    assert config.emitters.pytest.style == "factory"
    assert config.emitters.pytest.scope == "module"
    assert config.json.indent == 0
    assert config.json.orjson is True
    assert config.overrides["app.models.User"]["email"]["provider"] == "email"
    assert config.field_policies == ()
    assert config.locale_policies == ()
    assert config.paths.default_os == "windows"
    assert config.paths.model_targets == (("app.models.*", "mac"),)


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed")
def test_yaml_merges_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PFG_LOCALE", raising=False)

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
        [tool.pydantic_fixturegen]
        seed = "abc"
        locale = "en_GB"
        """,
        encoding="utf-8",
    )

    yaml_file = tmp_path / "pydantic-fixturegen.yaml"
    yaml_file.write_text(
        """
        include:
          - project.*
        emitters:
          pytest:
            style: class
        json:
          indent: 4
        """,
        encoding="utf-8",
    )

    config = load_config(root=tmp_path)

    assert config.seed == "abc"
    assert config.locale == "en_GB"
    assert config.include == ("project.*",)
    assert config.emitters.pytest.style == "class"
    assert config.json.indent == 4


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "PFG_LOCALE": "de_DE",
        "PFG_INCLUDE": "foo.*,bar.*",
        "PFG_P_NONE": "0.1",
        "PFG_EMITTERS__PYTEST__SCOPE": "session",
        "PFG_JSON__ORJSON": "true",
        "PFG_NOW": "2024-01-02T03:04:05Z",
    }

    config = load_config(root=tmp_path, env=env)

    assert config.locale == "de_DE"
    assert config.include == ("foo.*", "bar.*")
    assert config.p_none == pytest.approx(0.1)
    assert config.emitters.pytest.scope == "session"
    assert config.json.orjson is True
    assert config.now == datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    assert config.now == datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)


def test_env_overrides_validator_settings(tmp_path: Path) -> None:
    env = {
        "PFG_RESPECT_VALIDATORS": "true",
        "PFG_VALIDATOR_MAX_RETRIES": "3",
    }

    config = load_config(root=tmp_path, env=env)

    assert config.respect_validators is True
    assert config.validator_max_retries == 3


def test_cli_overrides_env(tmp_path: Path) -> None:
    env = {"PFG_LOCALE": "de_DE", "PFG_JSON__INDENT": "0"}
    cli = {"locale": "it_IT", "json": {"indent": 8}}

    config = load_config(root=tmp_path, env=env, cli=cli)

    assert config.locale == "it_IT"
    assert config.json.indent == 8


def test_cli_overrides_validator_settings(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={"respect_validators": True, "validator_max_retries": 7},
    )

    assert config.respect_validators is True
    assert config.validator_max_retries == 7


def test_env_overrides_nested_preserve_case(tmp_path: Path) -> None:
    env = {"PFG_OVERRIDES__app.models.User__Email__provider": "custom"}

    config = load_config(root=tmp_path, env=env)

    assert "app.models.User" in config.overrides
    assert "Email" in config.overrides["app.models.User"]
    assert config.overrides["app.models.User"]["Email"] == {"provider": "custom"}


def test_invalid_union_policy_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"union_policy": "never"})


def test_invalid_p_none_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"p_none": 2})


def test_invalid_path_target_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"paths": {"default_os": "solaris"}})


def test_invalid_path_models_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"paths": {"models": {"app.*": 123}}})


def test_yaml_requires_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_file = tmp_path / "pydantic-fixturegen.yaml"
    yaml_file.write_text("locale: fr_FR", encoding="utf-8")

    monkeypatch.setattr("pydantic_fixturegen.core.config.yaml", None)

    with pytest.raises(ConfigError):
        load_config(root=tmp_path)


def test_yaml_invalid_structure(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    yaml_file = tmp_path / "pydantic-fixturegen.yaml"
    yaml_file.write_text("- not a mapping", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(root=tmp_path)


def test_cli_invalid_include_sequence(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"include": [1, "ok"]})


def test_cli_invalid_seed_type(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"seed": ["not", "valid"]})


def test_cli_invalid_emitters_structure(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"emitters": {"pytest": "invalid"}})


def test_cli_invalid_json_options(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"json": {"orjson": "maybe"}})

    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"json": {"indent": -2}})


def test_cli_now_parses_iso(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"now": "2025-02-03T04:05:06Z"})

    assert config.now == datetime.datetime(2025, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc)


def test_cli_now_rejects_invalid(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"now": "not-a-time"})


def test_cli_now_accepts_datetime_instance(tmp_path: Path) -> None:
    value = datetime.datetime(2025, 1, 1, 12, 0, 0)
    config = load_config(root=tmp_path, cli={"now": value})

    assert config.now == value.replace(tzinfo=datetime.timezone.utc)


def test_field_policies_parsing(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={
            "field_policies": {
                "app.models.*.maybe": {"p_none": 0.0},
                "re:^app\\.models\\.User\\..*$": {"enum_policy": "random"},
            }
        },
    )

    assert len(config.field_policies) == 2
    patterns = [policy.pattern for policy in config.field_policies]
    assert "app.models.*.maybe" in patterns
    assert "re:^app\\.models\\.User\\..*$" in patterns
    first = config.field_policies[0]
    assert first.options["p_none"] == 0.0


def test_locale_policies_parsing(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={
            "locales": {
                "app.models.User.*": "sv_SE",
                "app.models.User.email": "en_GB",
            }
        },
    )

    assert len(config.locale_policies) == 2
    locales = {policy.pattern: policy.options["locale"] for policy in config.locale_policies}
    assert locales["app.models.User.*"] == "sv_SE"
    assert locales["app.models.User.email"] == "en_GB"


def test_locale_policies_invalid_locale(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"locales": {"*.name": "not_a_locale"}})


def test_field_policies_invalid_option(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            root=tmp_path,
            cli={"field_policies": {"*.value": {"unknown": 1}}},
        )


def test_array_config_parsing(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={
            "arrays": {
                "max_ndim": 3,
                "max_side": 5,
                "max_elements": 30,
                "dtypes": ["float32", "int16"],
            }
        },
    )

    assert config.arrays.max_ndim == 3
    assert config.arrays.max_side == 5
    assert config.arrays.max_elements == 30
    assert config.arrays.dtypes == ("float32", "int16")


def test_array_config_validation(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"arrays": {"max_ndim": 0}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"arrays": {"max_side": 0}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"arrays": {"max_elements": 0}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"arrays": {"dtypes": []}})


def test_identifier_config_parsing(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={
            "identifiers": {
                "secret_str_length": 12,
                "secret_bytes_length": 8,
                "url_schemes": ["http", "https"],
                "url_include_path": False,
                "uuid_version": 1,
                "mask_sensitive": True,
            }
        },
    )

    identifiers = config.identifiers
    assert identifiers.secret_str_length == 12
    assert identifiers.secret_bytes_length == 8
    assert identifiers.url_schemes == ("http", "https")
    assert identifiers.url_include_path is False
    assert identifiers.uuid_version == 1
    assert identifiers.mask_sensitive is True


def test_identifier_config_validation(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"secret_str_length": 0}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"secret_bytes_length": "not-int"}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"url_schemes": []}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"url_include_path": "yes"}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"uuid_version": 5}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"identifiers": {"mask_sensitive": "on"}})


def test_numbers_config_parsing(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={
            "numbers": {
                "distribution": "normal",
                "normal_stddev_fraction": 0.5,
                "spike_ratio": 0.2,
                "spike_width_fraction": 0.05,
            }
        },
    )

    numbers = config.numbers
    assert numbers.distribution == "normal"
    assert numbers.normal_stddev_fraction == pytest.approx(0.5)
    assert numbers.spike_ratio == pytest.approx(0.2)
    assert numbers.spike_width_fraction == pytest.approx(0.05)


def test_numbers_config_validation(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"numbers": {"distribution": "unknown"}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"numbers": {"normal_stddev_fraction": 0}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"numbers": {"spike_ratio": 2}})
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"numbers": {"spike_width_fraction": 0}})


def test_profile_applies_privacy_settings(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"profile": "pii-safe"})

    assert config.profile == "pii-safe"
    assert config.identifiers.mask_sensitive is True
    assert any(policy.pattern == "*.email" for policy in config.field_policies)


def test_profile_validation(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"profile": "unknown-profile"})


def test_preset_applies_policies(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"preset": "boundary"})

    assert config.preset == "boundary"
    assert config.union_policy == "random"
    assert config.enum_policy == "random"
    assert config.p_none == pytest.approx(0.35)


def test_preset_respects_overrides(tmp_path: Path) -> None:
    config = load_config(
        root=tmp_path,
        cli={"preset": "boundary", "union_policy": "first", "p_none": 0.1},
    )

    assert config.preset == "boundary"
    assert config.union_policy == "first"
    assert config.p_none == pytest.approx(0.1)


def test_unknown_preset_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"preset": "does-not-exist"})


def test_overrides_must_be_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"overrides": ["not", "mapping"]})

    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"overrides": {123: {}}})


def test_env_value_coercion_helpers() -> None:
    env = {
        "PFG_FLAG": "true",
        "PFG_NUMBER": "7",
        "PFG_RATIO": "0.75",
        "PFG_LIST": "alpha, beta , gamma",
        "PFG_EMITTERS__PYTEST__STYLE": "hybrid",
    }

    load_env_config = cast(Callable[[dict[str, str]], dict[str, Any]], config_mod._load_env_config)
    result = load_env_config(env)

    assert result["flag"] is True
    assert result["number"] == 7
    assert result["ratio"] == pytest.approx(0.75)
    assert result["list"] == ["alpha", "beta", "gamma"]
    assert result["emitters"]["pytest"]["style"] == "hybrid"


def test_invalid_p_none_string(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"p_none": "not-a-number"})


def test_invalid_locale_type(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"locale": 123})


def test_include_non_iterable(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"include": 123})


def test_union_policy_non_string(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"union_policy": 1})


def test_override_field_name_must_be_string(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"overrides": {"Model": {123: "value"}}})


def test_emitters_partial_defaults(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"emitters": {"pytest": {"scope": "session"}}})

    assert config.emitters.pytest.scope == "session"
    assert config.emitters.pytest.style == PytestEmitterConfig().style


def test_json_configuration_merges(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"json": {"indent": 4, "orjson": False}})

    assert config.json.indent == 4
    assert config.json.orjson is False


def test_json_invalid_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"json": "invalid"})


def test_json_indent_conversion_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"json": {"indent": "abc"}})


def test_boolean_false_string(tmp_path: Path) -> None:
    config = load_config(root=tmp_path, cli={"json": {"orjson": "false"}})

    assert config.json.orjson is False


def test_ensure_mutable_handles_nested() -> None:
    data = {"a": {"b": 1}, "c": [{"d": 2}]}

    ensure_mutable = cast(
        Callable[[dict[str, Any]], dict[str, Any]],
        config_mod._ensure_mutable,
    )
    result = ensure_mutable(data)

    assert result["a"]["b"] == 1
    assert result["c"][0]["d"] == 2


def test_deep_merge_merges_nested() -> None:
    target: dict[str, Any] = {"a": {"b": 1}, "list": [1]}
    source = {"a": {"c": 2}, "list": [1, 2], "d": 3}

    deep_merge = cast(
        Callable[[dict[str, Any], dict[str, Any]], None],
        config_mod._deep_merge,
    )
    deep_merge(target, source)

    assert target["a"]["b"] == 1
    assert target["a"]["c"] == 2
    assert target["list"] == [1, 2]
    assert target["d"] == 3


def test_config_helper_defaults() -> None:
    assert config_mod._coerce_str(None, "locale") == config_mod.DEFAULT_CONFIG.locale
    assert config_mod._normalize_sequence(None) == ()
    assert config_mod._coerce_datetime(None, "now") is None
    assert config_mod._coerce_datetime(" none ", "now") is None
    assert config_mod._normalize_overrides(None) == {}
    assert config_mod._normalize_field_policies(None) == ()
    assert config_mod._normalize_locale_policies(None) == ()
    assert config_mod._normalize_emitters(None).pytest == config_mod.EmittersConfig().pytest
    assert config_mod._normalize_json(None) == config_mod.JsonConfig()
    assert config_mod._normalize_array_config(None) == config_mod.ArrayConfig()
    assert config_mod._normalize_identifier_config(None) == config_mod.IdentifierConfig()
    assert config_mod._normalize_path_config(None) == config_mod.PathConfig()
    assert config_mod._coerce_bool(None, "json.orjson") == config_mod.DEFAULT_CONFIG.json.orjson
    assert (
        config_mod._coerce_optional_str(None, "emitters.pytest.style")
        == config_mod.DEFAULT_CONFIG.emitters.pytest.style
    )
    assert config_mod._coerce_indent(None) == config_mod.JsonConfig().indent
    assert config_mod._coerce_preset_value(" ") is None


def test_config_helper_non_default_branches() -> None:
    emitters = config_mod._normalize_emitters({"pytest": {"style": "factory", "scope": "module"}})
    assert emitters.pytest.style == "factory"

    array_cfg = config_mod._normalize_array_config(
        {"max_ndim": "3", "max_side": "5", "max_elements": "10", "dtypes": "float32,int"}
    )
    assert array_cfg.max_ndim == 3 and array_cfg.dtypes == ("float32", "int")

    identifier_cfg = config_mod._normalize_identifier_config(
        {
            "secret_str_length": "12",
            "secret_bytes_length": "6",
            "url_schemes": ["http", "https"],
            "url_include_path": True,
            "uuid_version": 4,
        }
    )
    assert identifier_cfg.secret_bytes_length == 6

    path_cfg = config_mod._normalize_path_config(
        {"default_os": "mac", "models": {"app.*": "windows"}}
    )
    assert path_cfg.default_os == "mac" and path_cfg.model_targets == (("app.*", "windows"),)

    assert config_mod._coerce_bool("TRUE", "json.orjson") is True
    with pytest.raises(ConfigError):
        config_mod._coerce_bool("maybe", "json.orjson")


def test_merge_source_with_preset_variants() -> None:
    data: dict[str, Any] = {"json": {"indent": 2}}
    config_mod._merge_source_with_preset(data, {"preset": None})
    assert data["preset"] is None

    data2: dict[str, Any] = {}
    config_mod._merge_source_with_preset(data2, {"preset": "boundary"})
    assert data2["preset"] == "boundary"
    assert "p_none" in data2  # preset settings merged


def test_coerce_env_value_parses_types() -> None:
    assert config_mod._coerce_env_value(" true ") is True
    assert config_mod._coerce_env_value("off") is False
    assert config_mod._coerce_env_value("a, b , c") == ["a", "b", "c"]
    assert config_mod._coerce_env_value("42") == 42
    assert config_mod._coerce_env_value("3.14") == pytest.approx(3.14)
    assert config_mod._coerce_env_value("text") == "text"


def test_normalize_sequence_and_policy_validation() -> None:
    assert config_mod._normalize_sequence("a, b") == ("a", "b")
    assert config_mod._normalize_sequence(["c", "d"]) == ("c", "d")
    with pytest.raises(ConfigError):
        config_mod._normalize_sequence([1, 2])
    with pytest.raises(ConfigError):
        config_mod._normalize_sequence(123)

    allowed = {"first", "random"}
    assert (
        config_mod._coerce_policy(None, allowed, "union_policy")
        == config_mod.DEFAULT_CONFIG.union_policy
    )
    with pytest.raises(ConfigError):
        config_mod._coerce_policy("invalid", allowed, "union_policy")


def test_coerce_datetime_accepts_multiple_inputs() -> None:
    naive = datetime.datetime(2024, 1, 1, 12, 0, 0)
    coerced = config_mod._coerce_datetime(naive, "now")
    assert coerced.tzinfo == datetime.timezone.utc

    date_only = datetime.date(2024, 1, 2)
    date_coerced = config_mod._coerce_datetime(date_only, "now")
    assert date_coerced.tzinfo == datetime.timezone.utc

    text = config_mod._coerce_datetime("2024-01-03T01:02:03Z", "now")
    assert text.tzinfo == datetime.timezone.utc

    with pytest.raises(ConfigError):
        config_mod._coerce_datetime("bad", "now")


def test_normalize_overrides_and_field_policy_errors() -> None:
    overrides = config_mod._normalize_overrides({"Model": {"field": {"provider": "faker"}}})
    assert overrides["Model"]["field"]["provider"] == "faker"

    with pytest.raises(ConfigError):
        config_mod._normalize_overrides({"Model": []})

    with pytest.raises(ConfigError):
        config_mod._normalize_field_policies({"": {}})


def test_normalize_identifier_config_and_errors() -> None:
    config = config_mod._normalize_identifier_config(
        {
            "secret_str_length": "12",
            "secret_bytes_length": "8",
            "url_schemes": "http, https",
            "url_include_path": False,
            "uuid_version": 4,
        }
    )
    assert config.secret_str_length == 12
    assert config.secret_bytes_length == 8
    assert config.url_schemes == ("http", "https")
    assert config.url_include_path is False

    with pytest.raises(ConfigError):
        config_mod._normalize_identifier_config({"url_schemes": []})


def test_normalize_path_config_targets_and_errors() -> None:
    config = config_mod._normalize_path_config(
        {"default_os": "mac", "models": {"pkg.*": "windows"}}
    )
    assert config.default_os == "mac"
    assert config.model_targets == (("pkg.*", "windows"),)

    with pytest.raises(ConfigError):
        config_mod._normalize_path_config({"models": {"pkg.*": "unsupported"}})


def test_coerce_path_target_and_indent() -> None:
    assert config_mod._coerce_path_target(" POSIX ", "paths.default_os") == "posix"
    with pytest.raises(ConfigError):
        config_mod._coerce_path_target("unknown", "paths.default_os")

    assert config_mod._coerce_indent("2") == 2
    with pytest.raises(ConfigError):
        config_mod._coerce_indent("not-int")
