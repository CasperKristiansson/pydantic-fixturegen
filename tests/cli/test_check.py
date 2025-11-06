from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import check as check_mod
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from tests._cli import create_cli_runner


runner = create_cli_runner()


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


def test_check_rejects_directory_target(tmp_path: Path) -> None:
    directory = tmp_path / "package"
    directory.mkdir()

    result = runner.invoke(cli_app, ["check", str(directory)])

    assert result.exit_code == 10
    assert "Target must be a Python module file" in result.stderr


def test_check_handles_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)

    def broken_config(*, root: Path) -> None:  # noqa: ARG001 - signature matches target
        raise check_mod.ConfigError("broken configuration")

    monkeypatch.setattr(check_mod, "load_config", broken_config)

    result = runner.invoke(cli_app, ["check", str(module_path)])

    assert result.exit_code == 10
    assert "broken configuration" in result.stderr


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


def test_execute_check_skips_blank_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module_path = _write_module(tmp_path)

    monkeypatch.setattr(check_mod, "load_config", lambda **_: None)
    monkeypatch.setattr(check_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        check_mod,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=[], warnings=["   "], errors=[]),
    )

    with pytest.raises(check_mod.DiscoveryError):
        check_mod._execute_check(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=64,
            json_out=None,
            fixtures_out=None,
            schema_out=None,
        )

    captured = capsys.readouterr()
    assert "warning:" not in captured.err


def test_execute_check_raises_discovery_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)

    monkeypatch.setattr(check_mod, "load_config", lambda **_: None)
    monkeypatch.setattr(check_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        check_mod,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(
            models=[], warnings=[], errors=["failed to import"]
        ),
    )

    with pytest.raises(check_mod.DiscoveryError) as exc_info:
        check_mod._execute_check(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=64,
            json_out=None,
            fixtures_out=None,
            schema_out=None,
        )

    assert "failed to import" in str(exc_info.value)


def test_execute_check_requires_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module_path = _write_module(tmp_path)

    monkeypatch.setattr(check_mod, "load_config", lambda **_: None)
    monkeypatch.setattr(check_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        check_mod,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=[], warnings=["notice"], errors=[]),
    )

    with pytest.raises(check_mod.DiscoveryError):
        check_mod._execute_check(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=64,
            json_out=None,
            fixtures_out=None,
            schema_out=None,
        )

    assert "notice" in capsys.readouterr().err


def test_execute_check_wraps_load_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(check_mod, "load_config", lambda **_: None)
    monkeypatch.setattr(check_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        check_mod,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=[info], warnings=[], errors=[]),
    )
    monkeypatch.setattr(
        check_mod,
        "load_model_class",
        lambda _model: (_ for _ in ()).throw(RuntimeError("import failure")),
    )

    with pytest.raises(check_mod.DiscoveryError) as exc_info:
        check_mod._execute_check(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=64,
            json_out=None,
            fixtures_out=None,
            schema_out=None,
        )

    assert "import failure" in str(exc_info.value)


def test_validate_output_targets_raises(tmp_path: Path) -> None:
    with pytest.raises(check_mod.DiscoveryError):
        check_mod._validate_output_targets([(tmp_path, "JSON output")])


def test_resolve_method_variants() -> None:
    with pytest.raises(check_mod.DiscoveryError):
        check_mod._resolve_method(ast_mode=True, hybrid_mode=True)

    assert check_mod._resolve_method(ast_mode=False, hybrid_mode=True) == "hybrid"
    assert check_mod._resolve_method(ast_mode=True, hybrid_mode=False) == "ast"
    assert check_mod._resolve_method(ast_mode=False, hybrid_mode=False) == "import"


def test_validate_output_path_conditions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory_issue = check_mod._validate_output_path(tmp_path, "JSON output")
    assert "points to a directory" in directory_issue[0]

    missing_parent = check_mod._validate_output_path(
        tmp_path / "missing" / "file.json", "JSON output"
    )
    assert "does not exist" in missing_parent[0]

    parent_file = tmp_path / "file.txt"
    parent_file.write_text("content", encoding="utf-8")
    not_dir = check_mod._validate_output_path(parent_file / "child.json", "JSON output")
    assert "not a directory" in not_dir[0]

    monkeypatch.setattr("pydantic_fixturegen.cli.check.os.access", lambda *_args, **_kwargs: False)
    not_writable = check_mod._validate_output_path(tmp_path / "file.json", "JSON output")
    assert "not writable" in not_writable[0]


def test_check_validates_output_paths(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "items.json"
    fixtures_out = tmp_path / "fixtures" / "test_items.py"
    schema_out = tmp_path / "schema" / "items.json"

    (tmp_path / "artifacts").mkdir()
    fixtures_out.parent.mkdir()
    schema_out.parent.mkdir()
    json_out.write_text("[]", encoding="utf-8")

    result = runner.invoke(
        cli_app,
        [
            "check",
            "--json-out",
            str(json_out),
            "--fixtures-out",
            str(fixtures_out),
            "--schema-out",
            str(schema_out),
            str(module_path),
        ],
    )

    assert result.exit_code == 0
    assert "Emitter destinations verified." in result.stdout
