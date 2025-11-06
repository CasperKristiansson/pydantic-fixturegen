"""Test utilities for CLI runners."""

from __future__ import annotations

from typer.testing import CliRunner


def create_cli_runner() -> CliRunner:
    """Instantiate a CliRunner while supporting older Click versions."""

    try:
        return CliRunner(mix_stderr=False)
    except TypeError:  # pragma: no cover - exercised in CI environments
        return CliRunner()
