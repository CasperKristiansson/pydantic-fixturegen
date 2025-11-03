from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import schema as schema_mod
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from typer.testing import CliRunner

runner = CliRunner()


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Address(BaseModel):
    city: str
    zip_code: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class Product(BaseModel):
    sku: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_schema_single_model(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "user_schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["title"] == "User"
    assert "properties" in payload


def test_gen_schema_combined_models(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "bundle.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"Address", "Product", "User"}


def test_gen_schema_indent_override(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "compact.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.Address",
            "--indent",
            "0",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert "\n" not in text


def test_gen_schema_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    output = tmp_path / "schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(missing),
            "--out",
            str(output),
            "--json-errors",
        ],
    )

    assert result.exit_code == 10
    assert "Target path" in result.stdout


def test_gen_schema_emit_artifact_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.emit_artifact",
        lambda *args, **kwargs: True,
    )

    def fail_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("emit_model_schema should not be called")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.schema.emit_model_schema", fail_emit)
    monkeypatch.setattr("pydantic_fixturegen.cli.gen.schema.emit_models_schema", fail_emit)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0
    assert not output.exists()


def test_gen_schema_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    def bad_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        raise RuntimeError("bad")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.schema.emit_model_schema", bad_emit)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 30
    assert "bad" in result.stderr


def test_gen_schema_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    def bad_config(**_: object):  # noqa: ANN003
        raise ConfigError("broken")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.schema.load_config", bad_config)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 10
    assert "broken" in result.stderr


def test_execute_schema_command_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module_path = _write_module(tmp_path)

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(models=[], warnings=["warn"], errors=[])

    monkeypatch.setattr(schema_mod, "discover_models", fake_discover)
    monkeypatch.setattr(schema_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(schema_mod, "load_entrypoint_plugins", lambda: None)

    with pytest.raises(DiscoveryError):
        schema_mod._execute_schema_command(
            target=str(module_path),
            out=module_path,
            indent=None,
            include=None,
            exclude=None,
        )

    captured = capsys.readouterr()
    assert "warn" in captured.err


def test_execute_schema_command_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(
            models=[
                IntrospectedModel(
                    module="pkg",
                    name="User",
                    qualname="pkg.User",
                    locator=str(module_path),
                    lineno=1,
                    discovery="import",
                    is_public=True,
                )
            ],
            warnings=[],
            errors=["boom"],
        )

    monkeypatch.setattr(schema_mod, "discover_models", fake_discover)
    monkeypatch.setattr(schema_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(schema_mod, "load_entrypoint_plugins", lambda: None)

    with pytest.raises(DiscoveryError):
        schema_mod._execute_schema_command(
            target=str(module_path),
            out=module_path,
            indent=None,
            include=None,
            exclude=None,
        )


def test_execute_schema_command_load_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    info = IntrospectedModel(
        module="pkg",
        name="User",
        qualname="pkg.User",
        locator=str(module_path),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    monkeypatch.setattr(schema_mod, "discover_models", fake_discover)
    monkeypatch.setattr(schema_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(schema_mod, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(
        schema_mod,
        "load_model_class",
        lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(DiscoveryError):
        schema_mod._execute_schema_command(
            target=str(module_path),
            out=module_path,
            indent=None,
            include=None,
            exclude=None,
        )
