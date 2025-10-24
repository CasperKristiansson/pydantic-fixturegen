from __future__ import annotations

import types

import pytest
from pydantic_fixturegen import cli as cli_pkg
from typer.testing import CliRunner

runner = CliRunner()


def test_load_typer_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.SimpleNamespace(bad="not-typer")
    monkeypatch.setattr(cli_pkg, "import_module", lambda _: module)

    with pytest.raises(TypeError):
        cli_pkg._load_typer("pkg:bad")


def test_root_invokes_list(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_invoke(import_path: str, ctx) -> None:  # noqa: ANN001
        calls.append(import_path)

    monkeypatch.setattr(cli_pkg, "_invoke", fake_invoke)

    result = runner.invoke(cli_pkg.app, [])
    assert result.exit_code == 0
    assert calls == ["pydantic_fixturegen.cli.list:app"]
