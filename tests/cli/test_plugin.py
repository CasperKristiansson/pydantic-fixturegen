from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli.plugin import app as plugin_app
from typer.testing import CliRunner

runner = CliRunner()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plugin_scaffold_creates_expected_layout(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(plugin_app, ["--directory", str(target), "demo"])

    assert result.exit_code == 0
    assert "Plugin scaffold created" in result.stdout

    pyproject = target / "pyproject.toml"
    providers = target / "src" / "demo" / "providers.py"
    workflow = target / ".github" / "workflows" / "ci.yml"

    assert pyproject.is_file()
    assert (target / "README.md").is_file()
    assert (target / "tests" / "test_plugin.py").is_file()
    assert providers.is_file()
    assert workflow.is_file()

    pyproject_content = _read(pyproject)
    assert 'name = "pfg-demo"' in pyproject_content
    assert 'demo = "demo.plugin:plugin"' in pyproject_content
    assert '"pydantic-fixturegen>=' in pyproject_content
    assert '"pytest>=8.3"' in pyproject_content

    workflow_content = _read(workflow)
    assert "pytest" in workflow_content


def test_plugin_scaffold_supports_namespace_and_overrides(tmp_path: Path) -> None:
    target = tmp_path / "custom"
    result = runner.invoke(
        plugin_app,
        [
            "--namespace",
            "acme.plugins",
            "--distribution",
            "acme-fixturegen-email",
            "--entrypoint",
            "acme-email",
            "--directory",
            str(target),
            "email",
        ],
    )

    assert result.exit_code == 0

    package = target / "src" / "acme" / "plugins" / "email"
    assert package.is_dir()
    assert (package / "__init__.py").is_file()

    tests_file = target / "tests" / "test_plugin.py"
    content = _read(tests_file)
    assert "from acme.plugins.email.plugin import plugin" in content

    pyproject = _read(target / "pyproject.toml")
    assert 'name = "acme-fixturegen-email"' in pyproject
    assert 'acme-email = "acme.plugins.email.plugin:plugin"' in pyproject


def test_existing_directory_without_force_errors(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(plugin_app, ["--directory", str(target), "demo"])

    assert result.exit_code != 0
    assert "--force to overwrite" in result.stderr
