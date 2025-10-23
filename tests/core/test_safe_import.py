from __future__ import annotations

import textwrap
from pathlib import Path

from pydantic_fixturegen.core.safe_import import EXIT_TIMEOUT, safe_import_models


def _write_module(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return module_path


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
