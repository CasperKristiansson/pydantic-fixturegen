from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import doctor as doctor_mod
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
    street: str
    city: str


class User(BaseModel):
    name: str
    age: int
    address: Address
""",
        encoding="utf-8",
    )
    return module_path


def test_doctor_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "Coverage: 3/3 fields" in result.stdout
    assert "Issues: none" in result.stdout


def test_doctor_reports_provider_issue(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Note(BaseModel):
    payload: object
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "type 'any'" in result.stdout.lower()


def test_doctor_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        ["doctor", "--json-errors", str(missing)],
    )

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout


def test_execute_doctor_path_checks(tmp_path: Path) -> None:
    not_there = tmp_path / "missing.py"
    with pytest.raises(DiscoveryError):
        doctor_mod._execute_doctor(
            target=str(not_there),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=256,
        )

    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(DiscoveryError):
        doctor_mod._execute_doctor(
            target=str(directory),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=256,
        )


def test_doctor_warnings_and_no_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = tmp_path / "empty.py"
    module.write_text("", encoding="utf-8")

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[], warnings=["unused"], errors=[])

    monkeypatch.setattr(doctor_mod, "discover_models", fake_discover)
    monkeypatch.setattr(doctor_mod, "clear_module_cache", lambda: None)

    doctor_mod._execute_doctor(
        target=str(module),
        include=None,
        exclude=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=1.0,
        memory_limit_mb=128,
    )

    captured = capsys.readouterr()
    assert "warning: unused" in captured.err
    assert "No models discovered." in captured.out


def test_doctor_resolve_method_conflict() -> None:
    with pytest.raises(DiscoveryError):
        doctor_mod._resolve_method(ast_mode=True, hybrid_mode=True)


def test_doctor_load_model_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    info = IntrospectedModel(
        module="pkg",
        name="Missing",
        qualname="pkg.Missing",
        locator=str(module),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    monkeypatch.setattr(doctor_mod, "discover_models", fake_discover)
    monkeypatch.setattr(doctor_mod, "clear_module_cache", lambda: None)

    def boom_loader(_: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(doctor_mod, "load_model_class", boom_loader)

    with pytest.raises(DiscoveryError, match="boom"):
        doctor_mod._execute_doctor(
            target=str(module),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
        )


def test_doctor_render_report_with_issues(capsys: pytest.CaptureFixture[str]) -> None:
    class Dummy(BaseModel):
        value: int

    report = doctor_mod.ModelReport(
        model=Dummy,
        coverage=(1, 2),
        issues=["problem"],
    )

    doctor_mod._render_report([report])
    captured = capsys.readouterr()
    assert "Coverage: 1/2" in captured.out
    assert "problem" in captured.out
