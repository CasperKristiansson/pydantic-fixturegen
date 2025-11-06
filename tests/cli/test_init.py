from __future__ import annotations

from pathlib import Path

import pytest
import typer
from pydantic_fixturegen.cli import init as init_mod
from pydantic_fixturegen.cli.init import app as init_app
from typer.testing import CliRunner

runner = CliRunner(mix_stderr=False)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_init_scaffolds_pyproject_and_directories(tmp_path: Path) -> None:
    result = runner.invoke(init_app, [str(tmp_path)])

    assert result.exit_code == 0

    pyproject = tmp_path / "pyproject.toml"
    assert pyproject.is_file()
    content = _read(pyproject)
    assert "[tool.pydantic_fixturegen]" in content
    assert "seed = 42" in content
    assert "[tool.pydantic_fixturegen.json]" in content

    fixtures_dir = tmp_path / "tests" / "fixtures"
    assert fixtures_dir.is_dir()
    assert (fixtures_dir / ".gitkeep").is_file()


def test_init_skips_existing_config_without_force(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
        [tool.pydantic_fixturegen]
        seed = 1
        """,
        encoding="utf-8",
    )

    result = runner.invoke(init_app, [str(tmp_path)])

    assert result.exit_code == 0
    content = _read(pyproject)
    assert content.count("[tool.pydantic_fixturegen]") == 1
    assert "seed = 1" in content


def test_init_force_rewrites_existing_config(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
        [tool.pydantic_fixturegen]
        seed = 99

        [tool.pydantic_fixturegen.json]
        indent = 0
        """,
        encoding="utf-8",
    )

    result = runner.invoke(init_app, ["--force", str(tmp_path)])

    assert result.exit_code == 0
    content = _read(pyproject)
    assert "seed = 42" in content
    assert "indent = 0" not in content


def test_init_can_emit_yaml_only(tmp_path: Path) -> None:
    result = runner.invoke(init_app, ["--no-pyproject", "--yaml", str(tmp_path)])

    assert result.exit_code == 0
    yaml_path = tmp_path / "pydantic-fixturegen.yaml"
    assert yaml_path.is_file()
    content = _read(yaml_path)
    assert "seed: 42" in content
    assert "emitters:" in content


def test_init_errors_without_outputs(tmp_path: Path) -> None:
    result = runner.invoke(init_app, ["--no-pyproject", "--no-yaml", str(tmp_path)])

    assert result.exit_code == 1
    assert "Nothing to scaffold" in (result.stdout + result.stderr)


def test_init_custom_options(tmp_path: Path) -> None:
    custom_yaml = tmp_path / "config" / "pfg.yaml"
    fixtures_dir = tmp_path / "custom" / "fixtures"

    result = runner.invoke(
        init_app,
        [
            "--yaml",
            "--yaml-path",
            str(custom_yaml),
            "--fixtures-dir",
            str(fixtures_dir),
            "--no-gitkeep",
            "--seed",
            "-1",
            "--locale",
            "sv_SE",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0

    pyproject = tmp_path / "pyproject.toml"
    content = _read(pyproject)
    assert "seed" not in content
    assert 'locale = "sv_SE"' in content

    yaml_content = _read(custom_yaml)
    assert "locale: sv_SE" in yaml_content

    assert fixtures_dir.is_dir()
    assert not (fixtures_dir / ".gitkeep").exists()


def test_init_invalid_style(tmp_path: Path) -> None:
    result = runner.invoke(init_app, ["--pytest-style", "invalid", str(tmp_path)])

    assert result.exit_code != 0
    assert "Invalid value" in (result.stdout + result.stderr)


def test_strip_pyproject_section_removes_config() -> None:
    original = (
        "[tool.other]\nvalue = 1\n\n\n"
        "[tool.pydantic_fixturegen]\nseed = 1\n\n\n"
        "[tool.more]\nvalue = 2\n"
    )

    cleaned = init_mod._strip_pyproject_section(original)

    assert "pydantic_fixturegen" not in cleaned
    assert "tool.other" in cleaned and "tool.more" in cleaned
    assert "\n\n\n" not in cleaned


def test_validate_choice_behaviour() -> None:
    assert init_mod._validate_choice("FACTORY", init_mod.PYTEST_STYLES, "pytest_style") == "factory"

    with pytest.raises(typer.BadParameter):
        init_mod._validate_choice("unknown", init_mod.PYTEST_STYLES, "pytest_style")


def test_ensure_directory_raises_on_file(tmp_path: Path) -> None:
    file_path = tmp_path / "existing"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(typer.BadParameter):
        init_mod._ensure_directory(file_path)


def test_format_relative_when_outside(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path.parent / "external"

    assert init_mod._format_relative(outside, root) == str(outside)


def test_write_pyproject_rejects_directory(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.mkdir()

    config = init_mod.InitConfig(
        seed=1,
        locale="en_US",
        union_policy="weighted",
        enum_policy="random",
        json_indent=2,
        json_orjson=False,
        pytest_style="functions",
        pytest_scope="function",
    )

    with pytest.raises(typer.BadParameter):
        init_mod._write_pyproject(tmp_path, config, force=False)


def test_write_yaml_rejects_directory(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.mkdir()

    config = init_mod.InitConfig(
        seed=1,
        locale="en_US",
        union_policy="weighted",
        enum_policy="random",
        json_indent=2,
        json_orjson=False,
        pytest_style="functions",
        pytest_scope="function",
    )

    with pytest.raises(typer.BadParameter):
        init_mod._write_yaml(target, config, force=False)


def test_write_yaml_skips_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("seed: 1\n", encoding="utf-8")

    config = init_mod.InitConfig(
        seed=1,
        locale="en_US",
        union_policy="weighted",
        enum_policy="random",
        json_indent=2,
        json_orjson=False,
        pytest_style="functions",
        pytest_scope="function",
    )

    result = init_mod._write_yaml(target, config, force=False)
    assert result is not None
    assert result.skipped and not result.wrote


def test_init_relative_yaml_path(tmp_path: Path) -> None:
    rel_yaml = Path("config/pfg.yaml")

    result = runner.invoke(
        init_app,
        ["--yaml", "--yaml-path", str(rel_yaml), str(tmp_path)],
    )

    assert result.exit_code == 0
    assert (tmp_path / rel_yaml).is_file()


def test_init_gitkeep_ensured(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    gitkeep = fixtures_dir / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")

    result = runner.invoke(init_app, [str(tmp_path)])

    assert result.exit_code == 0
    assert "Ensured tests/fixtures/.gitkeep" in result.stdout


def test_init_no_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True)

    monkeypatch.setattr(init_mod, "_write_pyproject", lambda *args, **kwargs: None)

    result = runner.invoke(init_app, ["--no-gitkeep", str(tmp_path)])

    assert result.exit_code == 0
    assert "No changes were necessary." in result.stdout
