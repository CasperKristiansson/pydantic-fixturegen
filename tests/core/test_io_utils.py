from __future__ import annotations

import os
from pathlib import Path

import pytest

from pydantic_fixturegen.core.io_utils import WriteResult, write_atomic_bytes, write_atomic_text


def test_write_atomic_text_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "example.txt"
    result = write_atomic_text(path, "hello world", hash_compare=True)

    assert isinstance(result, WriteResult)
    assert result.wrote is True
    assert result.skipped is False
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_atomic_text_skips_when_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "repeat.txt"
    write_atomic_text(path, "same-content", hash_compare=True)
    mtime_before = path.stat().st_mtime

    result = write_atomic_text(path, "same-content", hash_compare=True)

    assert result.wrote is False
    assert result.skipped is True
    assert result.reason == "unchanged"
    assert path.stat().st_mtime == pytest.approx(mtime_before)


def test_write_atomic_bytes(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    payload = b"\x00\x01\x02"
    result = write_atomic_bytes(path, payload, hash_compare=True)

    assert result.wrote is True
    assert path.read_bytes() == payload


def test_write_atomic_cleanup_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "failure.txt"
    write_atomic_text(path, "initial")

    captured: dict[str, Path] = {}

    def fake_replace(src: str, dst: str) -> None:
        captured["temp"] = Path(src)
        raise RuntimeError("replace failed")

    monkeypatch.setattr(os, "replace", fake_replace)

    with pytest.raises(RuntimeError):
        write_atomic_text(path, "updated")

    assert not captured["temp"].exists()
    assert path.read_text(encoding="utf-8") == "initial"
