from __future__ import annotations

import types

import pytest
import typer
from pydantic_fixturegen import cli as cli_pkg
from tests._cli import create_cli_runner

runner = create_cli_runner()


def test_load_typer_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sub_app = typer.Typer()
    module = types.SimpleNamespace(app=sub_app)
    monkeypatch.setattr(cli_pkg, "import_module", lambda module_name: module)

    loaded = cli_pkg._load_typer("pkg:app")

    assert loaded is sub_app


def test_invoke_routes_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_args: list[object] = []

    sub_app = typer.Typer()
    command = types.SimpleNamespace(
        main=lambda *, args, prog_name, standalone_mode: captured_args.append(
            (args, prog_name, standalone_mode)
        )
    )
    monkeypatch.setattr(cli_pkg, "_load_typer", lambda import_path: sub_app)
    monkeypatch.setattr(cli_pkg, "get_command", lambda _: command)

    ctx = types.SimpleNamespace(args=("alpha", "--flag"), command_path="pfg foo")
    cli_pkg._invoke("pkg:app", ctx)

    assert captured_args == [(["alpha", "--flag"], "pfg foo", False)]


def test_invoke_translates_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    sub_app = typer.Typer()
    command = types.SimpleNamespace(
        main=lambda **_: 5,
    )
    monkeypatch.setattr(cli_pkg, "_load_typer", lambda import_path: sub_app)
    monkeypatch.setattr(cli_pkg, "get_command", lambda _: command)

    ctx = types.SimpleNamespace(args=(), command_path="pfg foo")
    with pytest.raises(typer.Exit) as exc_info:
        cli_pkg._invoke("pkg:app", ctx)

    assert exc_info.value.exit_code == 5


def test_proxy_wires_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, list[str]]] = []

    def fake_invoke(import_path: str, ctx: typer.Context) -> None:
        seen.append((import_path, list(ctx.args)))

    monkeypatch.setattr(cli_pkg, "_invoke", fake_invoke)

    before = len(cli_pkg.app.registered_commands)
    cli_pkg._proxy("sample", "pkg.path:app", "sample help text")

    try:
        result = runner.invoke(cli_pkg.app, ["sample", "one", "two"])
        assert result.exit_code == 0
        assert seen == [("pkg.path:app", ["one", "two"])]
        new_command = cli_pkg.app.registered_commands[-1]
        assert new_command.name == "sample"
        assert new_command.callback.__doc__ == "sample help text"
    finally:
        cli_pkg.app.registered_commands = cli_pkg.app.registered_commands[:before]
