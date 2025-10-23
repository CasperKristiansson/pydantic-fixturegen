"""Basic import tests for the package skeleton."""

from __future__ import annotations

import importlib


def test_package_importable() -> None:
    """Ensure the top-level package can be imported."""
    module = importlib.import_module("pydantic_fixturegen")
    assert module.__name__ == "pydantic_fixturegen"


def test_cli_namespace_importable() -> None:
    """Ensure the CLI namespace package can be imported."""
    module = importlib.import_module("pydantic_fixturegen.cli")
    assert module.__name__ == "pydantic_fixturegen.cli"
