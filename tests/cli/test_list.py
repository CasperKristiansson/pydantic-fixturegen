from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.cli.list import app as list_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_source(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


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
