from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

LIST_MODULE = """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int


class Order(BaseModel):
    total: float
"""


def _write_module(tmp_path: Path, content: str = LIST_MODULE, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


def test_list_command_outputs_models(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()

    result = runner.invoke(cli_app, ["list", str(module_path)])

    assert result.exit_code == 0, result.output
    assert "models.User" in result.output
    assert "models.Order" in result.output


def test_explain_command_emits_json(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "explain",
            "--json",
            "--include",
            "models.User",
            str(module_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    names = {f"{entry['module']}.{entry['name']}" for entry in payload["models"]}
    assert "models.User" in names


def test_doctor_command_reports_success(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "doctor",
            "--include",
            "models.User",
            str(module_path),
        ],
    )
    assert result.exit_code == 0, result.output


def test_doctor_fail_on_gaps_exits_with_error(tmp_path: Path) -> None:
    source = """
from pydantic import BaseModel


class User(BaseModel):
    coords: complex
"""

    module_path = _write_module(tmp_path, source)
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "doctor",
            "--include",
            "models.User",
            "--fail-on-gaps",
            "0",
            str(module_path),
        ],
    )
    assert result.exit_code == 2
    assert "No provider" in result.output


def test_schema_config_command_writes_file(tmp_path: Path) -> None:
    runner = create_cli_runner()
    out_path = tmp_path / "schema" / "config.json"

    result = runner.invoke(
        cli_app,
        [
            "schema",
            "config",
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "$id" in payload


def test_init_scaffolds_configuration(tmp_path: Path) -> None:
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "init",
            str(tmp_path),
            "--pyproject",
            "--yaml",
            "--fixtures-dir",
            "tests/fixtures",
        ],
    )
    assert result.exit_code == 0, result.output

    pyproject = tmp_path / "pyproject.toml"
    yaml_config = tmp_path / "pydantic-fixturegen.yaml"
    fixtures_dir = tmp_path / "tests" / "fixtures"
    assert pyproject.exists()
    assert yaml_config.exists()
    assert fixtures_dir.is_dir()


def test_plugin_new_scaffolds_project(tmp_path: Path) -> None:
    runner = create_cli_runner()
    target = tmp_path / "plugins" / "demo"

    result = runner.invoke(
        cli_app,
        [
            "plugin",
            "--directory",
            str(target),
            "--namespace",
            "acme.tools",
            "--description",
            "Demo plugin",
            "--author",
            "QA",
            "demo-plugin",
        ],
    )
    assert result.exit_code == 0, result.output

    pyproject = target / "pyproject.toml"
    providers = target / "src" / "acme" / "tools" / "demo_plugin" / "providers.py"
    tests_dir = target / "tests" / "test_plugin.py"
    assert pyproject.exists()
    assert providers.exists()
    assert tests_dir.exists()


def test_check_command_reports_success(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    fixtures_path = tmp_path / "fixtures.py"
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "check",
            "--fixtures-out",
            str(fixtures_path),
            "--include",
            "models.User",
            str(module_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Configuration OK" in result.output
