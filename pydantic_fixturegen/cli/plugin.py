"""CLI utilities for scaffolding provider plugin projects."""

from __future__ import annotations

import re
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import typer

from pydantic_fixturegen.core.io_utils import WriteResult, write_atomic_text
from pydantic_fixturegen.core.version import get_tool_version

app = typer.Typer(help="Scaffold provider plugin projects.")

DEFAULT_VERSION = "0.1.0"
DEFAULT_LICENSE = "MIT"

NAME_ARGUMENT = typer.Argument(..., help="Base name for the plugin distribution.")
DIRECTORY_OPTION = typer.Option(
    None,
    "--directory",
    "-d",
    help="Directory to create (defaults to derived distribution name).",
)
NAMESPACE_OPTION = typer.Option(
    None,
    "--namespace",
    "-n",
    help="Optional dotted namespace for the Python package (for example: acme.plugins).",
)
DISTRIBUTION_OPTION = typer.Option(
    None,
    "--distribution",
    help="Override the PyPI distribution name.",
)
ENTRYPOINT_OPTION = typer.Option(
    None,
    "--entrypoint",
    help="Override the Pluggy entry point name (defaults to the slug).",
)
DESCRIPTION_OPTION = typer.Option(
    None,
    "--description",
    help="Project description written to pyproject metadata.",
)
AUTHOR_OPTION = typer.Option(
    None,
    "--author",
    help="Author name added to pyproject metadata.",
)
VERSION_OPTION = typer.Option(
    DEFAULT_VERSION,
    "--version",
    help="Initial version for the scaffolded distribution.",
)
LICENSE_OPTION = typer.Option(
    DEFAULT_LICENSE,
    "--license",
    help="License text written to pyproject metadata.",
)
FORCE_OPTION = typer.Option(
    False,
    "--force",
    help="Overwrite existing files when the target directory already exists.",
)


@dataclass(slots=True)
class PluginContext:
    """Normalized values describing the scaffolded plugin."""

    slug: str
    distribution: str
    entrypoint: str
    package_parts: tuple[str, ...]
    package_dotted: str
    package_path: str
    class_name: str
    description: str
    author: str
    version: str
    license: str
    tool_version: str
    display_name: str
    target: Path


def _normalize_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise typer.BadParameter("Name must contain at least one ASCII letter or number.")
    return normalized


def _normalize_identifier(value: str, *, field: str) -> str:
    simplified = value.strip().replace("-", "_")
    simplified = re.sub(r"[^0-9a-zA-Z_]", "", simplified)
    if not simplified:
        raise typer.BadParameter(f"{field} segment {value!r} is empty after normalization.")
    if simplified[0].isdigit():
        simplified = f"_{simplified}"
    if not simplified.isidentifier():
        raise typer.BadParameter(f"{field} segment {value!r} is not a valid identifier.")
    return simplified


def _split_namespace(namespace: str | None) -> tuple[str, ...]:
    if not namespace:
        return ()

    parts = [part for token in namespace.split(".") for part in token.split("/")]
    if not parts:
        return ()

    normalized_parts = tuple(_normalize_identifier(part, field="namespace") for part in parts)
    return normalized_parts


def _infer_distribution(slug: str, namespace_parts: Iterable[str], override: str | None) -> str:
    if override:
        derived = override.strip()
    else:
        prefix = "-".join(namespace_parts)
        derived = f"{prefix}-{slug}" if prefix else f"pfg-{slug}"

    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", derived).strip("-")
    if not normalized:
        raise typer.BadParameter("Distribution name becomes empty after normalization.")
    return normalized


def _infer_entrypoint(slug: str, override: str | None) -> str:
    normalized = override.strip() if override else slug.replace("_", "-")
    entry = re.sub(r"[^a-zA-Z0-9_.-]+", "-", normalized).strip("-")
    if not entry:
        raise typer.BadParameter("Entry point name becomes empty after normalization.")
    return entry


def _class_name_from_slug(slug: str) -> str:
    tokens = re.split(r"[-_]+", slug)
    class_name = "".join(token.capitalize() for token in tokens if token)
    return class_name or "Plugin"


def _format_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _ensure_directory(path: Path, *, force: bool) -> None:
    if path.exists():
        if not path.is_dir():
            raise typer.BadParameter(f"Target path {path} exists and is not a directory.")
        if not force:
            has_files = any(path.iterdir())
            if has_files:
                raise typer.BadParameter(
                    f"Directory {path} already exists. Use --force to overwrite."
                )
    else:
        path.mkdir(parents=True, exist_ok=True)


def _write_file(path: Path, content: str, *, force: bool) -> WriteResult:
    if path.exists() and not force:
        raise typer.BadParameter(
            f"{path} already exists. Use --force to overwrite specific files or "
            "run in an empty directory."
        )
    return write_atomic_text(path, content, hash_compare=True)


def _build_context(
    *,
    name: str,
    directory: Path | None,
    namespace: str | None,
    distribution: str | None,
    entrypoint: str | None,
    description: str | None,
    author: str | None,
    version: str,
    license_name: str,
) -> PluginContext:
    slug = _normalize_slug(name)
    namespace_parts = _split_namespace(namespace)
    distribution_name = _infer_distribution(slug, namespace_parts, distribution)
    entrypoint_name = _infer_entrypoint(slug, entrypoint)
    package_suffix = _normalize_identifier(slug.replace("-", "_"), field="package name")
    package_parts = namespace_parts + (package_suffix,)
    package_dotted = ".".join(package_parts)
    package_path = "/".join(package_parts)
    class_name = _class_name_from_slug(slug)
    display = " ".join(token.capitalize() for token in slug.split("-"))
    author_name = author or f"{display} Developers"
    summary = description or f"Custom pydantic-fixturegen providers for {display}."
    target_dir = directory or (Path.cwd() / distribution_name)

    return PluginContext(
        slug=slug,
        distribution=distribution_name,
        entrypoint=entrypoint_name,
        package_parts=package_parts,
        package_dotted=package_dotted,
        package_path=package_path,
        class_name=class_name,
        description=summary,
        author=author_name,
        version=version,
        license=license_name,
        tool_version=get_tool_version(),
        display_name=display,
        target=target_dir,
    )


def _pyproject_content(ctx: PluginContext) -> str:
    deps_line = f'  "pydantic-fixturegen>={ctx.tool_version}",'
    packages = f"src/{ctx.package_path}"
    include = f'"src/{ctx.package_path}"'
    return (
        textwrap.dedent(
            f"""
        [build-system]
        requires = ["hatchling>=1.24"]
        build-backend = "hatchling.build"

        [project]
        name = "{ctx.distribution}"
        version = "{ctx.version}"
        description = "{ctx.description}"
        readme = "README.md"
        requires-python = ">=3.10"
        license = {{ text = "{ctx.license}" }}
        authors = [{{ name = "{ctx.author}" }}]
        keywords = ["pydantic", "fixtures", "plugin"]
        dependencies = [
        {deps_line}
        ]

        [project.entry-points."pydantic_fixturegen"]
        {ctx.entrypoint} = "{ctx.package_dotted}.plugin:plugin"

        [project.optional-dependencies]
        test = ["pytest>=8.3"]

        [tool.hatch.build.targets.wheel]
        packages = ["{packages}"]

        [tool.hatch.build.targets.sdist]
        include = [
          {include},
          "tests",
          "README.md",
        ]
        """
        ).strip()
        + "\n"
    )


def _readme_content(ctx: PluginContext) -> str:
    provider_path = f"src/{ctx.package_path}/providers.py"
    return (
        textwrap.dedent(
            f"""
        # {ctx.display_name} plugin

        This project packages custom providers for [pydantic-fixturegen](https://github.com/CasperKristiansson/pydantic-fixturegen).
        It exposes a Pluggy plugin via the `pydantic_fixturegen` entry point `{ctx.entrypoint}`.

        ## Quick start

        1. Install dependencies locally:
           ```bash
           pip install -e ".[test]"
           ```
        2. Add or customize providers in `{provider_path}`.
        3. Run `pytest` to exercise the sample provider tests.

        ## Publishing

        Update `pyproject.toml` with project URLs and upload the distribution to a
        private index or PyPI.
        """
        ).strip()
        + "\n"
    )


def _plugin_content(ctx: PluginContext) -> str:
    return (
        textwrap.dedent(
            f"""
        \"\"\"Pluggy entry point for {ctx.display_name}.\"\"\"

        from __future__ import annotations

        from pydantic_fixturegen.core.providers.registry import ProviderRegistry
        from pydantic_fixturegen.plugins.hookspecs import hookimpl

        from . import providers


        class {ctx.class_name}:
            \"\"\"Register custom providers for pydantic-fixturegen.\"\"\"

            @hookimpl
            def pfg_register_providers(self, registry: ProviderRegistry) -> None:
                providers.register(registry)


        plugin = {ctx.class_name}()

        __all__ = ["plugin", "{ctx.class_name}"]
        """
        ).strip()
        + "\n"
    )


def _providers_content(ctx: PluginContext) -> str:
    entry_name = ctx.entrypoint.replace("-", "_").replace(".", "_")
    return (
        textwrap.dedent(
            f"""
        \"\"\"Sample providers bundled with {ctx.display_name}.\"\"\"

        from __future__ import annotations

        from faker import Faker

        from pydantic_fixturegen.core.providers.registry import ProviderRegistry
        from pydantic_fixturegen.core.schema import FieldSummary


        def favorite_color(summary: FieldSummary, *, faker: Faker | None = None) -> str:
            \"\"\"Return a color value for ``summary`` fields.\"\"\"

            fake = faker or Faker()
            return fake.safe_color_name()


        def register(registry: ProviderRegistry) -> None:
            \"\"\"Register providers with the supplied registry.\"\"\"

            registry.register(
                "string",
                favorite_color,
                name="{entry_name}.favorite_color",
                metadata={{"description": "Example provider - replace with your own."}},
            )
        """
        ).strip()
        + "\n"
    )


def _package_init_content(ctx: PluginContext) -> str:
    return (
        textwrap.dedent(
            f"""
        \"\"\"Public exports for {ctx.display_name}.\"\"\"

        from .plugin import plugin

        __all__ = ["plugin"]
        """
        ).strip()
        + "\n"
    )


def _tests_content(ctx: PluginContext) -> str:
    dotted = ctx.package_dotted
    return (
        textwrap.dedent(
            f"""
        from __future__ import annotations

        from pydantic_fixturegen.core.providers.registry import ProviderRegistry

        from {dotted}.plugin import plugin


        def test_plugin_registers_provider() -> None:
            registry = ProviderRegistry()
            registry.register_plugin(plugin)

            provider = registry.get("string")
            assert provider is not None
        """
        ).strip()
        + "\n"
    )


def _ci_workflow_content() -> str:
    return (
        textwrap.dedent(
            """
        name: CI

        on:
          push:
            branches: ["main"]
          pull_request:

        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-python@v5
                with:
                  python-version: "3.11"
              - name: Install dependencies
                run: |
                  pip install --upgrade pip
                  pip install -e ".[test]"
              - name: Run tests
                run: pytest
        """
        ).strip()
        + "\n"
    )


@app.command()
def new(  # noqa: PLR0913 - CLI command surfaces multiple knobs
    name: str = NAME_ARGUMENT,
    directory: Path | None = DIRECTORY_OPTION,
    namespace: str | None = NAMESPACE_OPTION,
    distribution: str | None = DISTRIBUTION_OPTION,
    entrypoint: str | None = ENTRYPOINT_OPTION,
    description: str | None = DESCRIPTION_OPTION,
    author: str | None = AUTHOR_OPTION,
    version: str = VERSION_OPTION,
    license_name: str = LICENSE_OPTION,
    force: bool = FORCE_OPTION,
) -> None:
    """Create a pluggy provider plugin skeleton."""

    context = _build_context(
        name=name,
        directory=directory,
        namespace=namespace,
        distribution=distribution,
        entrypoint=entrypoint,
        description=description,
        author=author,
        version=version,
        license_name=license_name,
    )

    _ensure_directory(context.target, force=force)

    src_dir = context.target / "src" / Path(*context.package_parts)
    tests_dir = context.target / "tests"
    workflow_path = context.target / ".github" / "workflows"

    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    workflow_path.mkdir(parents=True, exist_ok=True)

    actions: list[str] = []

    files = {
        context.target / "pyproject.toml": _pyproject_content(context),
        context.target / "README.md": _readme_content(context),
        src_dir / "__init__.py": _package_init_content(context),
        src_dir / "providers.py": _providers_content(context),
        src_dir / "plugin.py": _plugin_content(context),
        tests_dir / "test_plugin.py": _tests_content(context),
        workflow_path / "ci.yml": _ci_workflow_content(),
    }

    for path, content in files.items():
        result = _write_file(path, content, force=force)
        if result.wrote:
            actions.append(f"Created {_format_relative(path, context.target)}")
        else:
            actions.append(f"Ensured {_format_relative(path, context.target)}")

    typer.secho("Plugin scaffold created:", fg=typer.colors.GREEN)
    for action in actions:
        typer.echo(f"  - {action}")
