from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli.init import app as init_app
from typer.testing import CliRunner

runner = CliRunner()


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
