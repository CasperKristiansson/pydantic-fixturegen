from __future__ import annotations

import os
import textwrap
from pathlib import Path

from pydantic_fixturegen.core.safe_import import EXIT_TIMEOUT, safe_import_models


def _write_module(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(textwrap.dedent(content), encoding="utf-8")
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


def test_safe_import_collects_pydantic_models(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        "sample",
        """
        from pydantic import BaseModel

        class User(BaseModel):
            id: int
            name: str
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is True
    assert result.exit_code == 0
    assert {model["name"] for model in result.models} == {"User"}


def test_safe_import_timeout(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        "sleeper",
        """
        import time

        time.sleep(2)
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path, timeout=0.3)

    assert result.success is False
    assert result.exit_code == EXIT_TIMEOUT
    assert "timed out" in (result.error or "")


def test_safe_import_blocks_network(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        "network",
        """
        import socket

        def attempt():
            s = socket.socket()
            try:
                s.connect(("example.com", 80))
            finally:
                s.close()

        attempt()
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is False
    assert "network access disabled" in (result.error or "")


def test_safe_import_handles_relative_imports(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)

    result = safe_import_models([target_module], cwd=tmp_path)

    assert result.success is True
    discovered = {model["name"] for model in result.models}
    assert {"ExampleInputs", "ExampleRequest"}.issubset(discovered)


def test_safe_import_handles_relative_imports_from_nested_cwd(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)
    package_dir = target_module.parent

    original_cwd = os.getcwd()
    os.chdir(package_dir)
    try:
        result = safe_import_models([target_module.name], cwd=package_dir)
    finally:
        os.chdir(original_cwd)

    assert result.success is True
    discovered = {model["name"] for model in result.models}
    assert {"ExampleInputs", "ExampleRequest"}.issubset(discovered)
