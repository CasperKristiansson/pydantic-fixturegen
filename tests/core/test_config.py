from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.core import config as config_mod
from pydantic_fixturegen.core.config import (
    AppConfig,
    ConfigError,
    JsonConfig,
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
    assert config.now is None


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


def test_cli_overrides_env(tmp_path: Path) -> None:
    env = {"PFG_LOCALE": "de_DE", "PFG_JSON__INDENT": "0"}
    cli = {"locale": "it_IT", "json": {"indent": 8}}

    config = load_config(root=tmp_path, env=env, cli=cli)

    assert config.locale == "it_IT"
    assert config.json.indent == 8


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

    result = config_mod._load_env_config(env)  # type: ignore[attr-defined]

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

    result = config_mod._ensure_mutable(data)  # type: ignore[attr-defined]

    assert result["a"]["b"] == 1
    assert result["c"][0]["d"] == 2


def test_deep_merge_merges_nested() -> None:
    target: dict[str, Any] = {"a": {"b": 1}, "list": [1]}
    source = {"a": {"c": 2}, "list": [1, 2], "d": 3}

    config_mod._deep_merge(target, source)  # type: ignore[attr-defined]

    assert target["a"]["b"] == 1
    assert target["a"]["c"] == 2
    assert target["list"] == [1, 2]
    assert target["d"] == 3
