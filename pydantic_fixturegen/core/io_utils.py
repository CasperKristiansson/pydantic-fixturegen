"""Filesystem utilities for atomic, hash-aware writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["WriteResult", "write_atomic_text", "write_atomic_bytes"]


@dataclass(slots=True)
class WriteResult:
    """Metadata describing the outcome of an atomic write."""

    path: Path
    wrote: bool
    skipped: bool
    reason: str | None = None


def write_atomic_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    hash_compare: bool = False,
) -> WriteResult:
    """Atomically write text content to ``path``."""

    data = content.encode(encoding)
    return _write_atomic(Path(path), data, hash_compare=hash_compare)


def write_atomic_bytes(
    path: str | Path,
    data: bytes,
    *,
    hash_compare: bool = False,
) -> WriteResult:
    """Atomically write binary content to ``path``."""

    return _write_atomic(Path(path), data, hash_compare=hash_compare)


def _write_atomic(path: Path, data: bytes, *, hash_compare: bool) -> WriteResult:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = _hash_bytes(data) if hash_compare else None
    if hash_compare and path.exists():
        existing = path.read_bytes()
        if _hash_bytes(existing) == digest:
            return WriteResult(path=path, wrote=False, skipped=True, reason="unchanged")

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        raise exc

    return WriteResult(path=path, wrote=True, skipped=False, reason=None)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
