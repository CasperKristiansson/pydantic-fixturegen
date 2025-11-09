from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen.core import config as config_mod
from pydantic_fixturegen.core.config import ConfigError


def test_load_env_config_supports_nested_keys() -> None:
    env = {
        "PFG_INCLUDE": "app.User",
        "PFG_JSON__INDENT": "4",
        "PFG_OVERRIDES__MyModel.*__extra": "value",
        "PFG_FIELD_POLICIES__*.email__P_NONE": "0.25",
    }
    loaded = config_mod._load_env_config(env)
    assert loaded["include"] == "app.User"
    assert loaded["json"]["indent"] == 4
    assert loaded["overrides"]["MyModel.*"]["extra"] == "value"
    assert loaded["field_policies"]["*.email"]["p_none"] == 0.25


def test_normalize_field_policies_invalid_pattern() -> None:
    with pytest.raises(ConfigError):
        config_mod._normalize_field_policies({"": {}})


def test_build_app_config_with_env_and_cli(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pydantic_fixturegen]
seed = 42
""",
        encoding="utf-8",
    )
    env = {
        "PFG_UNION_POLICY": "random",
        "PFG_FIELD_POLICIES__*.email__P_NONE": "0.1",
    }
    cli = {"include": ["app.User"], "max_depth": 5}
    cfg = config_mod.load_config(
        root=tmp_path,
        pyproject_path=pyproject,
        env=env,
        cli=cli,
    )
    assert cfg.seed == 42
    assert cfg.union_policy == "random"
    assert cfg.include == ("app.User",)
    assert cfg.max_depth == 5
    assert any(policy.pattern == "*.email" for policy in cfg.field_policies)


def test_coerce_env_value_handles_types() -> None:
    assert config_mod._coerce_env_value("true") is True
    assert config_mod._coerce_env_value("FALSE") is False
    assert config_mod._coerce_env_value("1,2 , 3") == ["1", "2", "3"]
    assert config_mod._coerce_env_value(" 25 ") == 25
    assert config_mod._coerce_env_value(" 2.5 ") == 2.5
    assert config_mod._coerce_env_value("text") == "text"


def test_set_nested_value_creates_mapping() -> None:
    mapping: dict[str, object] = {}
    config_mod._set_nested_value(mapping, "level1", "level2", 10)
    assert mapping == {"level1": {"level2": 10}}


def test_coerce_positive_int_errors_on_bool() -> None:
    with pytest.raises(ConfigError):
        config_mod._coerce_positive_int(True, field_name="test", default=1)


def test_load_config_from_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pydantic-fixturegen.yml"
    yaml_path.write_text(
        """
seed: 99
include:
  - app.Model
""",
        encoding="utf-8",
    )
    cfg = config_mod.load_config(
        root=tmp_path,
        pyproject_path=tmp_path / "pyproject.toml",
        yaml_path=yaml_path,
    )
    assert cfg.seed == 99
    assert cfg.include == ("app.Model",)


def test_normalize_overrides_and_errors() -> None:
    overrides = config_mod._normalize_overrides({"app.User": {"email": {"p_none": 0.2}}})
    assert overrides["app.User"]["email"]["p_none"] == 0.2
    with pytest.raises(ConfigError):
        config_mod._normalize_overrides({"app.User": ["invalid"]})


def test_normalize_locale_policies_invalid() -> None:
    with pytest.raises(ConfigError):
        config_mod._normalize_locale_policies({"*.email": ""})


def test_normalize_emitters_rejects_non_mapping() -> None:
    with pytest.raises(ConfigError):
        config_mod._normalize_emitters("invalid")


def test_normalize_json_rejects_non_mapping() -> None:
    with pytest.raises(ConfigError):
        config_mod._normalize_json("invalid")
