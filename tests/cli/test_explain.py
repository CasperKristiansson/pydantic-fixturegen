from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import explain as explain_mod
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.strategies import Strategy, UnionStrategy
from typer.testing import CliRunner

runner = CliRunner()


def _write_models(tmp_path: Path) -> Path:
    module = tmp_path / "models.py"
    module.write_text(
        """
from typing import Literal

from pydantic import BaseModel


class Profile(BaseModel):
    username: str
    active: bool


class User(BaseModel):
    name: str
    age: int
    profile: Profile
    role: Literal["admin", "user"]
""",
        encoding="utf-8",
    )
    return module


def test_explain_outputs_summary(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "explain",
            str(module),
        ],
    )

    assert result.exit_code == 0
    assert "models.User" in result.stdout
    assert "profile" in result.stdout
    assert "role" in result.stdout


def test_explain_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        ["gen", "explain", "--json-errors", str(missing)],
    )

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout


def test_execute_explain_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = tmp_path / "empty.py"
    module.write_text("", encoding="utf-8")

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[], warnings=["unused"], errors=[])

    monkeypatch.setattr(explain_mod, "discover_models", fake_discover)
    monkeypatch.setattr(explain_mod, "clear_module_cache", lambda: None)

    explain_mod._execute_explain(target=str(module), include=None, exclude=None)
    captured = capsys.readouterr()
    assert "warning: unused" in captured.err
    assert "No models discovered." in captured.out


def test_execute_explain_union_and_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    info = IntrospectedModel(
        module="pkg",
        name="Demo",
        qualname="pkg.Demo",
        locator=str(module),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    class DemoModel(BaseModel):
        name: str
        fails: int
        role: str

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    monkeypatch.setattr(explain_mod, "discover_models", fake_discover)
    monkeypatch.setattr(explain_mod, "load_model_class", lambda _: DemoModel)
    monkeypatch.setattr(explain_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(explain_mod, "create_default_registry", lambda load_plugins: object())

    class DummyBuilder:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def build_field_strategy(self, model, field_name, annotation, summary):  # noqa: ANN001, ANN201
            base_summary = FieldSummary(type="string", constraints=FieldConstraints())
            if field_name == "fails":
                raise ValueError("no provider")
            if field_name == "role":
                choice = Strategy(
                    field_name="role",
                    summary=base_summary,
                    annotation=str,
                    provider_ref=None,
                    provider_name="string.default",
                    provider_kwargs={},
                    p_none=0.0,
                )
                return UnionStrategy(field_name="role", choices=[choice], policy="first")
            return Strategy(
                field_name=field_name,
                summary=base_summary,
                annotation=str,
                provider_ref=None,
                provider_name="string.default",
                provider_kwargs={},
                p_none=0.0,
            )

    monkeypatch.setattr(explain_mod, "StrategyBuilder", lambda *args, **kwargs: DummyBuilder())

    explain_mod._execute_explain(target=str(module), include=None, exclude=None)
    captured = capsys.readouterr()
    assert "Model: test_explain.DemoModel" in captured.out
    assert "Field: fails" in captured.out
    assert "Union policy" in captured.out
