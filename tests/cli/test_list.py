from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
from pydantic_fixturegen.cli.list import _render_result, _resolve_method
from pydantic_fixturegen.cli.list import app as list_app
from pydantic_fixturegen.core.errors import DiscoveryError, UnsafeImportError
from pydantic_fixturegen.core.introspect import IntrospectionResult
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_source(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


def _write_relative_import_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "lib" / "models"
    package_root.mkdir(parents=True)

    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "__init__.py").write_text("", encoding="utf-8")

    (package_root / "shared_model.py").write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel

            class RangeModel(BaseModel):
                lower: float
                upper: float

            class FileRefModel(BaseModel):
                path: str
                label: str
            """
        ),
        encoding="utf-8",
    )

    target_module = package_root / "example_model.py"
    target_module.write_text(
        textwrap.dedent(
            """
            from typing import Literal

            from pydantic import BaseModel

            from .shared_model import FileRefModel, RangeModel


            class ExampleInputs(BaseModel):
                axis_unit: Literal["a", "b", "c"]
                region: RangeModel


            class ExampleRequest(BaseModel):
                project_id: str
                files: list[FileRefModel]
                inputs: ExampleInputs
            """
        ),
        encoding="utf-8",
    )

    return target_module


def test_list_ast_mode(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        "models",
        """
from pydantic import BaseModel

class Foo(BaseModel):
    id: int
""",
    )

    result = runner.invoke(list_app, ["--ast", str(path)])

    assert result.exit_code == 0
    assert "models.Foo [ast]" in result.stdout


def test_list_import_public_only(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        "accounts",
        """
from pydantic import BaseModel

class Account(BaseModel):
    id: int

class _Hidden(BaseModel):
    value: str
""",
    )

    result = runner.invoke(list_app, ["--public-only", str(path)])

    assert result.exit_code == 0
    assert "Account [import]" in result.stdout
    assert "_Hidden" not in result.stdout


def test_list_include_exclude(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        "items",
        """
from pydantic import BaseModel

class Alpha(BaseModel):
    value: int

class Beta(BaseModel):
    value: int
""",
    )

    result = runner.invoke(
        list_app,
        [
            "--ast",
            "--include",
            "items.Alpha",
            "--exclude",
            "*.Beta",
            str(path),
        ],
    )

    assert result.exit_code == 0
    assert "items.Alpha [ast]" in result.stdout
    assert "Beta" not in result.stdout


def test_list_flags_mutually_exclusive(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        "dual",
        """
from pydantic import BaseModel

class Sample(BaseModel):
    value: int
""",
    )

    result = runner.invoke(list_app, ["--ast", "--hybrid", str(path)])

    assert result.exit_code != 0
    assert "Choose only one" in result.stdout or result.stderr


def test_list_ast_emits_warning_on_parse_failure(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.py"
    bad_path.write_text("def ???", encoding="utf-8")

    result = runner.invoke(list_app, ["--ast", str(bad_path)])

    assert result.exit_code == 0
    assert "warning:" in result.stderr
    assert "No models discovered." in result.stdout


def test_list_import_timeout_reports_error(tmp_path: Path) -> None:
    sleeper = _write_source(
        tmp_path,
        "sleeper",
        """
import time
from pydantic import BaseModel

class Sleeper(BaseModel):
    id: int

time.sleep(1)
""",
    )

    result = runner.invoke(list_app, ["--timeout", "0.1", str(sleeper)])

    assert result.exit_code == 10
    assert "error" in result.stderr.lower() or "warning" in result.stderr.lower()


def test_list_handles_relative_imports(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)

    result = runner.invoke(list_app, [str(target_module)])

    assert result.exit_code == 0
    assert "lib.models.example_model.ExampleInputs [import]" in result.stdout
    assert "lib.models.example_model.ExampleRequest [import]" in result.stdout


def test_render_result_handles_network_errors() -> None:
    result = IntrospectionResult(models=[], warnings=[], errors=["Network unreachable"])
    with pytest.raises(UnsafeImportError):
        _render_result(result)


def test_render_result_handles_generic_errors() -> None:
    result = IntrospectionResult(models=[], warnings=[], errors=["Missing module"])
    with pytest.raises(DiscoveryError):
        _render_result(result)


def test_render_result_emits_warning_and_empty_notice(capsys) -> None:
    result = IntrospectionResult(models=[], warnings=["  caution  "], errors=[])
    _render_result(result)
    out, err = capsys.readouterr()
    assert "warning" in err.lower()
    assert "No models discovered." in out


def test_resolve_method_switches() -> None:
    assert _resolve_method(ast_mode=True, hybrid_mode=False) == "ast"
    assert _resolve_method(ast_mode=False, hybrid_mode=True) == "hybrid"
    assert _resolve_method(ast_mode=False, hybrid_mode=False) == "import"
    with pytest.raises(DiscoveryError):
        _resolve_method(ast_mode=True, hybrid_mode=True)


def test_list_handles_relative_imports_from_package_directory(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)
    package_dir = target_module.parent

    original_cwd = os.getcwd()
    os.chdir(package_dir)
    try:
        result = runner.invoke(list_app, [target_module.name])
    finally:
        os.chdir(original_cwd)

    assert result.exit_code == 0
    assert "lib.models.example_model.ExampleInputs [import]" in result.stdout
    assert "lib.models.example_model.ExampleRequest [import]" in result.stdout
