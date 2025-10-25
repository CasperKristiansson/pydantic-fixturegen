"""Helpers for implementing watch mode across CLI commands."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import cast

from pydantic_fixturegen.core.errors import WatchError
from pydantic_fixturegen.logging import get_logger

_CONFIG_FILENAMES = (
    Path("pyproject.toml"),
    Path("pydantic-fixturegen.yaml"),
    Path("pydantic-fixturegen.yml"),
)


def gather_default_watch_paths(
    target: Path,
    *,
    output: Path | None = None,
    extra: Iterable[Path] | None = None,
) -> list[Path]:
    """Collect filesystem locations to monitor for change events."""

    paths: set[Path] = set()
    target = target.resolve()
    paths.add(target)
    paths.add(target.parent)

    cwd = Path.cwd()
    for candidate in _CONFIG_FILENAMES:
        path = (cwd / candidate).resolve()
        if path.exists():
            paths.add(path)

    if output is not None:
        out_path = output.resolve()
        if out_path.exists():
            paths.add(out_path)
        parent = out_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        paths.add(parent)

    if extra:
        for candidate in extra:
            resolved = candidate.resolve()
            if resolved.exists():
                paths.add(resolved)
            parent = resolved.parent
            if parent.exists():
                paths.add(parent)

    normalized = _normalize_watch_paths(paths)
    if not normalized:
        raise WatchError("No valid paths available for watch mode.")
    return normalized


WatchIterator = Iterator[set[tuple[int, Path]]]
WatchBackend = Callable[..., WatchIterator]


def run_with_watch(
    run_once: Callable[[], None],
    watch_paths: Iterable[Path],
    *,
    debounce: float,
) -> None:
    """Execute ``run_once`` immediately and re-run when filesystem changes occur."""

    watch_fn: WatchBackend = _import_watch_backend()
    normalized = _normalize_watch_paths(watch_paths)
    if not normalized:
        raise WatchError("No valid paths available for watch mode.")

    run_once()
    logger = get_logger()
    logger.info(
        "Watch mode active. Press Ctrl+C to stop.",
        paths=[str(path) for path in normalized],
        debounce=debounce,
    )

    try:
        for changes in watch_fn(*normalized, debounce=debounce):
            changed_paths = sorted({str(path) for _, path in changes})
            logger.info("Detected changes", paths=changed_paths)
            run_once()
    except KeyboardInterrupt:
        logger.warn("Watch mode stopped.")


def _normalize_watch_paths(paths: Iterable[Path]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        candidate = path.resolve()
        monitor = candidate if candidate.exists() else candidate.parent
        if not monitor.exists():
            continue
        if monitor not in seen:
            normalized.append(monitor)
            seen.add(monitor)
    return normalized


def _import_watch_backend() -> WatchBackend:
    try:
        from watchfiles import watch as watch_fn  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise WatchError(
            "Watch mode requires the optional 'watchfiles' dependency. Install it via"
            " `pip install pydantic-fixturegen[watch]`."
        ) from exc
    return cast(WatchBackend, watch_fn)


__all__ = ["gather_default_watch_paths", "run_with_watch"]
