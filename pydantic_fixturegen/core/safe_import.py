"""Safe import runner that executes user modules in a constrained subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXIT_TIMEOUT = 40

_PROTECTED_ENV_KEYS = {
    "PYTHONPATH",
    "PYTHONSAFEPATH",
    "PYTHONNOUSERSITE",
    "NO_PROXY",
    "no_proxy",
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "TMPDIR",
    "TMP",
    "TEMP",
    "HOME",
}


@dataclass(slots=True)
class SafeImportResult:
    """Outcome from executing the safe import subprocess."""

    success: bool
    models: list[dict[str, Any]]
    error: str | None
    traceback: str | None
    stderr: str
    exit_code: int


def safe_import_models(
    paths: Sequence[Path | str],
    *,
    cwd: Path | str | None = None,
    timeout: float = 5.0,
    memory_limit_mb: int = 256,
    python_executable: str | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> SafeImportResult:
    """Import one or more modules in a sandboxed subprocess and collect Pydantic models.

    Args:
        paths: Iterable of file paths to Python modules.
        cwd: Working directory for the subprocess (defaults to current working directory).
        timeout: Seconds before the subprocess is terminated with exit code 40.
        memory_limit_mb: Soft memory cap applied inside the subprocess.
        python_executable: Python interpreter to use (defaults to `sys.executable`).
        extra_env: Additional environment variables to expose to the subprocess.
    """
    if not paths:
        return SafeImportResult(True, [], None, None, "", 0)

    workdir = Path(cwd) if cwd else Path.cwd()
    python = python_executable or sys.executable

    request = {
        "paths": [str(Path(path).resolve()) for path in paths],
        "memory_limit_mb": memory_limit_mb,
        "workdir": str(workdir.resolve()),
    }

    env = _build_env(workdir, extra_env)

    try:
        completed = subprocess.run(
            [python, "-c", _RUNNER_SNIPPET],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            env=env,
            cwd=str(workdir),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return SafeImportResult(
            success=False,
            models=[],
            error="Safe import timed out.",
            traceback=None,
            stderr=_safe_text(exc.stderr),
            exit_code=EXIT_TIMEOUT,
        )

    stdout = completed.stdout.strip()
    stderr = completed.stderr
    exit_code = completed.returncode

    if not stdout:
        return SafeImportResult(
            success=False,
            models=[],
            error="Safe import produced no output.",
            traceback=None,
            stderr=stderr,
            exit_code=exit_code or 1,
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return SafeImportResult(
            success=False,
            models=[],
            error=f"Failed to decode safe-import payload: {exc}",
            traceback=None,
            stderr=stderr,
            exit_code=exit_code or 1,
        )

    success = bool(payload.get("success"))
    models = payload.get("models") or []
    error = payload.get("error")
    traceback_text = payload.get("traceback")

    return SafeImportResult(
        success=success,
        models=models,
        error=error,
        traceback=traceback_text,
        stderr=stderr,
        exit_code=exit_code,
    )


# Internal helpers -----------------------------------------------------------------


def _safe_text(value: object) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value or "")


def _build_env(workdir: Path, extra_env: Mapping[str, str] | None) -> dict[str, str]:
    base_env: dict[str, str] = {
        "PYTHONSAFEPATH": "1",
        "PYTHONPATH": str(workdir),
        "NO_PROXY": "*",
        "no_proxy": "*",
        "http_proxy": "",
        "https_proxy": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "all_proxy": "",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(workdir),
        "TMP": str(workdir),
        "TEMP": str(workdir),
        "HOME": str(workdir),
    }

    allowed_passthrough = ["PATH", "SYSTEMROOT", "COMSPEC"]
    for key in allowed_passthrough:
        if key in os.environ:
            base_env[key] = os.environ[key]

    if extra_env:
        for key, value in extra_env.items():
            if key in _PROTECTED_ENV_KEYS:
                continue
            base_env[key] = value

    return base_env


_RUNNER_SNIPPET = textwrap.dedent(
    """
    import builtins
    import json
    import os
    import sys
    import traceback
    from importlib import util as importlib_util
    from pathlib import Path

    def _apply_resource_limits(limit_mb: int) -> None:
        try:
            import resource
        except ImportError:  # pragma: no cover
            return

        bytes_limit = max(1, limit_mb) * 1024 * 1024
        for res_name in ("RLIMIT_AS", "RLIMIT_DATA"):
            res = getattr(resource, res_name, None)
            if res is None:
                continue
            soft, hard = resource.getrlimit(res)
            hard_limit = bytes_limit
            if hard not in (resource.RLIM_INFINITY, None) and hard < bytes_limit:
                hard_limit = hard

            if soft in (resource.RLIM_INFINITY, None) or soft > hard_limit:
                soft_limit = hard_limit
            else:
                soft_limit = soft

            try:
                resource.setrlimit(res, (soft_limit, hard_limit))
            except (ValueError, OSError):  # pragma: no cover
                continue

    def _block_network() -> None:
        import socket

        class _ProtectedSocket(socket.socket):
            def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("network access disabled in safe-import")

            def connect(self, *args, **kwargs):  # type: ignore[override]
                raise RuntimeError("network access disabled in safe-import")

            def connect_ex(self, *args, **kwargs):  # type: ignore[override]
                raise RuntimeError("network access disabled in safe-import")

        def _blocked(*_args, **_kwargs):
            raise RuntimeError("network access disabled in safe-import")

        socket.socket = _ProtectedSocket  # type: ignore[assignment]
        socket.create_connection = _blocked  # type: ignore[assignment]
        socket.socketpair = _blocked  # type: ignore[assignment]
        socket.create_server = _blocked  # type: ignore[assignment]
        socket.getaddrinfo = _blocked  # type: ignore[assignment]
        socket.gethostbyname = _blocked  # type: ignore[assignment]
        socket.gethostbyaddr = _blocked  # type: ignore[assignment]


    def _restrict_filesystem(root: Path) -> None:
        import io

        allowed_root = root.resolve()

        def _normalize_candidate(candidate: object) -> Path | None:
            if isinstance(candidate, int):
                return None
            if isinstance(candidate, (str, bytes, os.PathLike)):
                path = Path(candidate)
            else:
                return None
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            else:
                path = path.resolve()
            return path

        def _ensure_allowed(candidate: object) -> None:
            normalized = _normalize_candidate(candidate)
            if normalized is None:
                return
            try:
                normalized.relative_to(allowed_root)
            except ValueError:
                raise RuntimeError("filesystem writes outside the sandbox are not permitted")

        def _needs_write(mode: str) -> bool:
            return any(flag in mode for flag in ("w", "a", "x", "+"))

        original_open = builtins.open

        def _guarded_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
            if _needs_write(mode):
                _ensure_allowed(file)
            return original_open(file, mode, *args, **kwargs)

        builtins.open = _guarded_open  # type: ignore[assignment]

        original_io_open = io.open

        def _guarded_io_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
            if _needs_write(mode):
                _ensure_allowed(file)
            return original_io_open(file, mode, *args, **kwargs)

        io.open = _guarded_io_open  # type: ignore[assignment]

        original_os_open = os.open

        def _guarded_os_open(path, flags, mode=0o777):  # type: ignore[no-untyped-def]
            needs_write = bool(
                flags
                & (
                    os.O_WRONLY
                    | os.O_RDWR
                    | os.O_APPEND
                    | os.O_CREAT
                    | os.O_TRUNC
                )
            )
            if needs_write:
                _ensure_allowed(path)
            return original_os_open(path, flags, mode)

        os.open = _guarded_os_open  # type: ignore[assignment]

        original_path_write_text = Path.write_text

        def _guarded_write_text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ensure_allowed(self)
            return original_path_write_text(self, *args, **kwargs)

        Path.write_text = _guarded_write_text  # type: ignore[assignment]

        original_path_write_bytes = Path.write_bytes

        def _guarded_write_bytes(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ensure_allowed(self)
            return original_path_write_bytes(self, *args, **kwargs)

        Path.write_bytes = _guarded_write_bytes  # type: ignore[assignment]

        original_path_touch = Path.touch

        def _guarded_touch(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ensure_allowed(self)
            return original_path_touch(self, *args, **kwargs)

        Path.touch = _guarded_touch  # type: ignore[assignment]

    def _derive_module_name(module_path: Path, index: int) -> str:
        stem = module_path.stem or "module"
        return stem if index == 0 else f"{stem}_{index}"

    def _load_module(module_path: Path, index: int):
        module_name = _derive_module_name(module_path, index)
        spec = importlib_util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {module_path}")
        module = importlib_util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _collect_models(module, module_path: Path):
        models = []
        try:
            from pydantic import BaseModel
        except Exception:  # pragma: no cover - in absence of pydantic
            BaseModel = None

        for attr_name, attr_value in vars(module).items():
            if getattr(attr_value, "__module__", None) != module.__name__:
                continue
            if BaseModel is None:
                continue
            if isinstance(attr_value, type) and issubclass(attr_value, BaseModel):
                models.append(
                    {
                        "module": module.__name__,
                        "name": attr_value.__name__,
                        "qualname": f"{module.__name__}.{attr_value.__name__}",
                        "path": str(module_path),
                    }
                )
        return models

    def main() -> None:
        request = json.loads(sys.stdin.read())

        workdir = Path(request.get("workdir") or os.getcwd())
        os.chdir(workdir)

        _apply_resource_limits(int(request.get("memory_limit_mb", 256)))
        _block_network()
        _restrict_filesystem(workdir)

        paths = [Path(path) for path in request.get("paths", [])]

        collected = []
        for idx, path in enumerate(paths):
            module_path = Path(path)
            module = _load_module(module_path, idx)
            collected.extend(_collect_models(module, module_path))

        payload = {"success": True, "models": collected}
        json.dump(payload, sys.stdout)

    if __name__ == "__main__":
        try:
            main()
        except Exception as exc:  # pragma: no cover
            payload = {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            json.dump(payload, sys.stdout)
    """
)
