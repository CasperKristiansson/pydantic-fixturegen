from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen.core import config as config_mod
from pydantic_fixturegen.core.config import ConfigError, load_config


def test_load_config_pyproject_missing(tmp_path: Path) -> None:
    config = load_config(pyproject_path=tmp_path / "missing.toml")
    assert config.locale == config_mod.DEFAULT_CONFIG.locale


def test_load_config_yaml_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_file = tmp_path / "pydantic-fixturegen.yml"
    yaml_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(config_mod, "yaml", None)
    with pytest.raises(ConfigError):
        load_config(root=tmp_path)


def test_load_config_invalid_cli_seed(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"seed": {"bad": True}})


def test_load_config_invalid_cli_json_indent(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(root=tmp_path, cli={"json": {"indent": -1}})
