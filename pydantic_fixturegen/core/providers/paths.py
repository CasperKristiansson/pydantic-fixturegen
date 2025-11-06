"""Filesystem path providers for pydantic-fixturegen."""

from __future__ import annotations

import random
import string
from collections.abc import Callable
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from pydantic_fixturegen.core.config import PathConfig
from pydantic_fixturegen.core.path_template import sanitize_path_segment
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary

_SEGMENT_CHARS = string.ascii_lowercase + string.digits
_WINDOWS_DRIVES = tuple("CDEFGHIJKLMNOPQRSTUVWXYZ")
_FILE_EXTENSIONS = ("txt", "log", "json", "yaml", "csv", "cfg", "ini", "data")

_PathBuilder = Callable[[random.Random, str], PurePath]


def generate_path(
    summary: FieldSummary,
    *,
    random_generator: random.Random | None = None,
    path_config: PathConfig | None = None,
    model_type: type[Any] | None = None,
) -> str:
    """Generate filesystem paths tailored to a target OS."""

    if random_generator is None:
        raise RuntimeError("Path provider requires a seeded random generator.")

    config = path_config or PathConfig()
    target_os = config.target_for(model_type)
    builder = _PATH_BUILDERS[target_os]
    kind = _determine_kind(summary)

    path_obj = builder(random_generator, kind)
    path_str = str(path_obj)
    constrained = _apply_length_constraints(path_str, summary.constraints, kind)
    return constrained


def register_path_providers(registry: ProviderRegistry) -> None:
    registry.register(
        "path",
        generate_path,
        name="path.default",
        metadata={"description": "Generate OS-specific filesystem paths."},
    )


def _determine_kind(summary: FieldSummary) -> str:
    if summary.format == "directory":
        return "directory"
    if summary.format == "file":
        return "file"
    return "file"


def _build_posix_path(rng: random.Random, kind: str) -> PurePath:
    base = rng.choice(
        (
            PurePosixPath("/var"),
            PurePosixPath("/usr/local"),
            PurePosixPath("/opt"),
            PurePosixPath("/srv"),
            PurePosixPath("/home"),
        )
    )
    if base == PurePosixPath("/home"):
        base = base / _posix_segment(rng)
    segment_count = rng.randint(1, 3)
    segments = [_posix_segment(rng) for _ in range(segment_count)]
    path = base
    for segment in segments:
        path = path / segment
    if kind != "directory":
        path = path / _file_name(rng, lowercase=True)
    return path


def _build_mac_path(rng: random.Random, kind: str) -> PurePath:
    choice = rng.choice(("users", "applications", "volumes"))
    if choice == "users":
        base = PurePosixPath("/Users") / _title_segment(rng)
        base = base / rng.choice(["Documents", "Library", "Projects"])
    elif choice == "applications":
        app_name = _title_segment(rng)
        base = PurePosixPath("/Applications") / f"{app_name}.app" / "Contents" / "Resources"
    else:
        base = PurePosixPath("/Volumes") / _title_segment(rng)
    if kind != "directory":
        base = base / _file_name(rng, lowercase=False)
    return base


def _build_windows_path(rng: random.Random, kind: str) -> PurePath:
    drive = rng.choice(_WINDOWS_DRIVES)
    root = PureWindowsPath(f"{drive}:\\")
    template = rng.choice(("Users", "ProgramData", "Projects"))
    if template == "Users":
        base = root / "Users" / _title_segment(rng)
    elif template == "ProgramData":
        base = root / "ProgramData" / _windows_segment(rng)
    else:
        base = root / _windows_segment(rng)
    extra_segments = rng.randint(1, 2)
    for _ in range(extra_segments):
        base = base / _windows_segment(rng)
    if kind != "directory":
        base = base / _file_name(rng, lowercase=False, uppercase_extension=True)
    return base


_PATH_BUILDERS: dict[str, _PathBuilder] = {
    "posix": _build_posix_path,
    "mac": _build_mac_path,
    "windows": _build_windows_path,
}


def _apply_length_constraints(path: str, constraints: FieldConstraints, kind: str) -> str:
    min_length = constraints.min_length or 0
    max_length = constraints.max_length

    adjusted = path
    if len(adjusted) < min_length:
        filler = sanitize_path_segment("x" * max(4, min_length - len(adjusted))) or "data"
        separator = "\\" if "\\" in adjusted else "/"
        if kind == "directory":
            adjusted = adjusted.rstrip("/\\") + separator + filler
        else:
            stem, ext = _split_extension(adjusted)
            adjusted = f"{stem}_{filler}{ext}"
        if len(adjusted) < min_length:
            adjusted += "x" * (min_length - len(adjusted))

    if max_length is not None and len(adjusted) > max_length:
        adjusted = adjusted[:max_length]
        adjusted = adjusted.rstrip("/\\")

    return adjusted or path


def _posix_segment(rng: random.Random) -> str:
    raw = "".join(rng.choice(_SEGMENT_CHARS) for _ in range(rng.randint(4, 10)))
    return sanitize_path_segment(raw) or "segment"


def _windows_segment(rng: random.Random) -> str:
    raw = "".join(rng.choice(_SEGMENT_CHARS) for _ in range(rng.randint(3, 9)))
    mixed = "".join(ch.upper() if rng.random() < 0.3 else ch for ch in raw)
    return sanitize_path_segment(mixed) or "Data"


def _title_segment(rng: random.Random) -> str:
    raw = "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 8)))
    sanitized = sanitize_path_segment(raw)
    return sanitized.capitalize() if sanitized else "Project"


def _file_name(
    rng: random.Random,
    *,
    lowercase: bool,
    uppercase_extension: bool = False,
) -> str:
    name_raw = "".join(rng.choice(_SEGMENT_CHARS) for _ in range(rng.randint(4, 10)))
    name = sanitize_path_segment(name_raw) or "file"
    if lowercase:
        name = name.lower()
    extension = rng.choice(_FILE_EXTENSIONS)
    if uppercase_extension:
        extension = extension.upper()
    return f"{name}.{extension}"


def _split_extension(path: str) -> tuple[str, str]:
    last_sep = max(path.rfind("/"), path.rfind("\\"))
    dot_index = path.rfind(".")
    if dot_index > last_sep:
        return path[:dot_index], path[dot_index:]
    return path, ""


__all__ = ["generate_path", "register_path_providers"]
