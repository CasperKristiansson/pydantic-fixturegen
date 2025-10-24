from __future__ import annotations

import textwrap
from pathlib import Path

from pydantic_fixturegen.core.safe_import import safe_import_models


def _write_module(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return module_path


def test_safe_import_blocks_network_socket_usage(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        "net_block",
        """
        import socket

        socket.create_connection(("example.com", 80))
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is False
    assert "network access disabled" in (result.error or "")


def test_safe_import_blocks_writes_outside_sandbox(tmp_path: Path) -> None:
    outside_target = tmp_path.parent / "should_not_exist.txt"
    module_path = _write_module(
        tmp_path,
        "fs_escape",
        f"""
        from pathlib import Path

        target = Path(r"{outside_target}")
        target.write_text("nope", encoding="utf-8")
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is False
    assert "filesystem writes outside the sandbox" in (result.error or "")
    assert not outside_target.exists()


def test_safe_import_allows_writes_inside_sandbox(tmp_path: Path) -> None:
    inside_target = tmp_path / "allowed.txt"
    module_path = _write_module(
        tmp_path,
        "fs_allowed",
        f"""
        from pathlib import Path

        target = Path(r"{inside_target}")
        target.write_text("ok", encoding="utf-8")
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is True
    assert result.models == []
    assert inside_target.read_text(encoding="utf-8") == "ok"


def test_safe_import_blocks_os_open_outside(tmp_path: Path) -> None:
    outside_target = tmp_path.parent / "os_open_forbidden.txt"
    module_path = _write_module(
        tmp_path,
        "fs_os_open",
        f"""
        import os
        from pathlib import Path

        fd = os.open(r"{outside_target}", os.O_WRONLY | os.O_CREAT, 0o644)
        os.write(fd, b"nope")
        os.close(fd)
        """,
    )

    result = safe_import_models([module_path], cwd=tmp_path)

    assert result.success is False
    assert "filesystem writes outside the sandbox" in (result.error or "")
    assert not outside_target.exists()
