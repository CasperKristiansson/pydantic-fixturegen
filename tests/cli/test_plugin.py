from __future__ import annotations

import re
from pathlib import Path

import pytest
import typer

from pydantic_fixturegen.cli import plugin as plugin_mod
from tests._cli import create_cli_runner

plugin_app = plugin_mod.app

runner = create_cli_runner()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _normalize_cli(text: str) -> str:
    """Collapse whitespace and box characters emitted by Typer/Rich."""

    stripped = _ANSI_RE.sub("", text)
    return " ".join(stripped.replace("│", " ").split())


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
    assert "--force to overwrite" in _normalize_cli(result.stderr)


def test_plugin_force_run_reports_ensured(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(plugin_app, ["--directory", str(target), "demo"])
    assert result.exit_code == 0

    second = runner.invoke(plugin_app, ["--directory", str(target), "--force", "demo"])
    assert second.exit_code == 0
    assert "Ensured pyproject.toml" in second.stdout


def test_normalize_slug_requires_alphanumeric() -> None:
    with pytest.raises(typer.BadParameter):
        plugin_mod._normalize_slug("!!!")


def test_normalize_identifier_rules() -> None:
    assert plugin_mod._normalize_identifier("1value", field="test") == "_1value"
    with pytest.raises(typer.BadParameter):
        plugin_mod._normalize_identifier("***", field="test")


def test_split_namespace_accepts_multiple_delimiters() -> None:
    parts = plugin_mod._split_namespace("acme.plugins/util")
    assert parts == ("acme", "plugins", "util")


def test_infer_distribution_validates_override() -> None:
    with pytest.raises(typer.BadParameter):
        plugin_mod._infer_distribution("slug", (), "!!!")


def test_infer_entrypoint_validates_override() -> None:
    with pytest.raises(typer.BadParameter):
        plugin_mod._infer_entrypoint("slug", "***")


def test_ensure_directory_rejects_file(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.write_text("blocked", encoding="utf-8")

    with pytest.raises(typer.BadParameter):
        plugin_mod._ensure_directory(target, force=False)


def test_ensure_directory_allows_empty_directory(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()

    plugin_mod._ensure_directory(target, force=False)
    assert target.is_dir()


def test_write_file_requires_force(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(typer.BadParameter):
        plugin_mod._write_file(target, "existing", force=False)


def test_format_relative_falls_back_to_absolute(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    other = tmp_path / "external" / "file.txt"
    other.parent.mkdir(parents=True)
    other.write_text("data", encoding="utf-8")

    assert plugin_mod._format_relative(other, root) == str(other)
