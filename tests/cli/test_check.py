from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import check as check_mod
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from typer.testing import CliRunner

runner = CliRunner()


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Item(BaseModel):
    name: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_check_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    result = runner.invoke(cli_app, ["check", str(module_path)])

    assert result.exit_code == 0
    assert "Configuration OK" in result.stdout
    assert "Discovered 1 model" in result.stdout
    assert "Check complete" in result.stdout


def test_check_emitter_path_validation(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing_parent = tmp_path / "does" / "not" / "exist.json"

    result = runner.invoke(
        cli_app,
        [
            "check",
            "--json-out",
            str(missing_parent),
            str(module_path),
        ],
    )

    assert result.exit_code == 10
    assert "does not exist" in result.stderr


def test_check_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(cli_app, ["check", "--json-errors", str(missing)])

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout
    assert "missing.py" in result.stdout


def test_check_emits_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    info = IntrospectedModel(
        module="pkg",
        name="Item",
        qualname="pkg.Item",
        locator=str(module_path),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    class Dummy(BaseModel):
        value: int

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert Path(path) == module_path
        return IntrospectionResult(models=[info], warnings=["warn"], errors=[])

    monkeypatch.setattr(check_mod, "discover_models", fake_discover)
    monkeypatch.setattr(check_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(check_mod, "load_model_class", lambda _: Dummy)

    result = runner.invoke(cli_app, ["check", str(module_path)])

    assert result.exit_code == 0
    assert "warn" in result.stderr
