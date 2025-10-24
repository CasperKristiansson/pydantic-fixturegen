"""Utilities for emitting generated instances to JSON/JSONL files."""

from __future__ import annotations

import dataclasses
import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

from pydantic import BaseModel

try:  # Optional dependency
    import orjson  # type: ignore
except ImportError:  # pragma: no cover - optional extra not installed
    orjson = None  # type: ignore[assignment]

DEFAULT_INDENT = 2
DEFAULT_SHARD_PAD = 5


@dataclass(slots=True)
class JsonEmitConfig:
    """Configuration options for JSON emission."""

    output_path: Path
    count: int
    jsonl: bool = False
    indent: int | None = DEFAULT_INDENT
    shard_size: int | None = None
    use_orjson: bool = False
    ensure_ascii: bool = False
    max_workers: int | None = None


def emit_json_samples(
    samples: Iterable[Any] | Callable[[], Any],
    *,
    output_path: str | Path,
    count: int,
    jsonl: bool = False,
    indent: int | None = DEFAULT_INDENT,
    shard_size: int | None = None,
    use_orjson: bool = False,
    ensure_ascii: bool = False,
    max_workers: int | None = None,
) -> list[Path]:
    """Emit generated samples to JSON or JSONL files.

    Args:
        samples: Iterable of pre-generated items or callable producing a new item
            when invoked (used ``count`` times).
        output_path: Target file path (single file) or stem used for sharded
            outputs. File suffix is normalised based on ``jsonl``.
        count: Number of samples to write.
        jsonl: Emit newline-delimited JSON instead of a JSON array.
        indent: Indentation level (``0``/``None`` -> compact). For JSONL it is
            ignored.
        shard_size: Maximum number of records per shard. ``None`` or ``<= 0``
            emits a single file.
        use_orjson: Serialise with orjson when available for performance.
        ensure_ascii: Force ASCII-only output when using the stdlib encoder.
        max_workers: Optional worker cap for concurrent shard writes.

    Returns:
        List of ``Path`` objects for the created file(s), ordered by shard index.
    """

    config = JsonEmitConfig(
        output_path=Path(output_path),
        count=count,
        jsonl=jsonl,
        indent=_normalise_indent(indent, jsonl=jsonl),
        shard_size=_normalise_shard_size(shard_size, count),
        use_orjson=use_orjson,
        ensure_ascii=ensure_ascii,
        max_workers=max_workers,
    )
    encoder = _JsonEncoder(
        indent=config.indent,
        ensure_ascii=config.ensure_ascii,
        use_orjson=config.use_orjson,
    )

    records = list(_collect_samples(samples, config.count))
    total = len(records)
    shards = _split_into_shards(records, config.shard_size)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[Path] = []
    with ThreadPoolExecutor(max_workers=_worker_count(config.max_workers, len(shards))) as executor:
        futures: list[Future[Path]] = []
        for index, chunk in enumerate(shards, start=1):
            futures.append(
                executor.submit(
                    _write_shard,
                    chunk,
                    config.output_path,
                    index,
                    len(shards),
                    config.jsonl,
                    encoder,
                )
            )
        for future in futures:
            results.append(future.result())

    if not results:
        # Ensure at least one file is produced even when there are no records.
        results.append(
            _write_empty_shard(
                config.output_path,
                config.jsonl,
                encoder,
            )
        )
    return results


# --------------------------------------------------------------------------- helpers
def _collect_samples(
    samples: Iterable[Any] | Callable[[], Any],
    count: int,
) -> Iterator[Any]:
    if count <= 0:
        return iter(())

    if callable(samples):
        def factory_iterator() -> Iterator[Any]:
            for _ in range(count):
                yield _normalise_record(samples())

        return factory_iterator()

    def iterable_iterator() -> Iterator[Any]:
        yielded = 0
        for item in samples:
            if yielded >= count:
                break
            yield _normalise_record(item)
            yielded += 1

    return iterable_iterator()


def _normalise_indent(indent: int | None, *, jsonl: bool) -> int | None:
    if jsonl:
        return None
    if indent in (None, 0):
        return None
    if indent < 0:
        raise ValueError("indent must be >= 0")
    return indent


def _normalise_shard_size(shard_size: int | None, count: int) -> int | None:
    if shard_size is None or shard_size <= 0:
        return None
    return max(1, min(shard_size, count)) if count > 0 else shard_size


def _split_into_shards(records: Sequence[Any], shard_size: int | None) -> list[list[Any]]:
    if not records:
        return []
    if shard_size is None:
        return [list(records)]

    shards: list[list[Any]] = []
    for start in range(0, len(records), shard_size):
        shards.append(list(records[start : start + shard_size]))
    return shards


def _worker_count(max_workers: int | None, shard_count: int) -> int:
    if shard_count <= 1:
        return 1
    if max_workers is not None:
        return max(1, min(max_workers, shard_count))
    return min(shard_count, (os_cpu_count() or 1) * 2)


def _write_shard(
    chunk: Sequence[Any],
    base_path: Path,
    shard_index: int,
    shard_count: int,
    jsonl: bool,
    encoder: "_JsonEncoder",
) -> Path:
    path = _shard_path(base_path, shard_index, shard_count, jsonl)
    payload = _prepare_payload(chunk, jsonl, encoder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _write_empty_shard(
    base_path: Path,
    jsonl: bool,
    encoder: "_JsonEncoder",
) -> Path:
    path = _shard_path(base_path, 1, 1, jsonl)
    empty_payload = "" if jsonl else encoder.encode([])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(empty_payload, encoding="utf-8")
    return path


def _prepare_payload(chunk: Sequence[Any], jsonl: bool, encoder: "_JsonEncoder") -> str:
    if jsonl:
        lines = [encoder.encode(item) for item in chunk]
        return "\n".join(lines) + ("\n" if lines else "")
    return encoder.encode(list(chunk))


def _shard_path(base_path: Path, shard_index: int, shard_count: int, jsonl: bool) -> Path:
    suffix = ".jsonl" if jsonl else ".json"
    if shard_count <= 1:
        return _ensure_suffix(base_path, suffix)
    stem = base_path.stem or base_path.name
    parent = base_path.parent
    return parent / f"{stem}-{shard_index:0{DEFAULT_SHARD_PAD}d}{suffix}"


def _ensure_suffix(path: Path, suffix: str) -> Path:
    if path.suffix:
        return path.with_suffix(suffix)
    return path.with_name(f"{path.name}{suffix}")


def _normalise_record(record: Any) -> Any:
    if dataclasses.is_dataclass(record):
        return dataclasses.asdict(record)
    if isinstance(record, BaseModel):
        return record.model_dump()
    if hasattr(record, "model_dump"):
        return record.model_dump()  # type: ignore[no-any-return]
    return record


class _JsonEncoder:
    def __init__(self, *, indent: int | None, ensure_ascii: bool, use_orjson: bool) -> None:
        self.indent = indent
        self.ensure_ascii = ensure_ascii
        self.use_orjson = use_orjson
        if use_orjson:
            if orjson is None:
                raise RuntimeError("orjson is not installed but use_orjson was requested.")
            self._options = _orjson_options(indent)
        else:
            self._options = None

    def encode(self, obj: Any) -> str:
        normalized = _normalise_record(obj)
        if self.use_orjson:
            return orjson.dumps(  # type: ignore[union-attr, no-any-return]
                normalized,
                option=self._options,
            ).decode("utf-8")
        return json.dumps(
            normalized,
            ensure_ascii=self.ensure_ascii,
            indent=self.indent,
            sort_keys=True,
        )


def _orjson_options(indent: int | None) -> int:
    options = orjson.OPT_SORT_KEYS  # type: ignore[union-attr]
    if indent:
        if indent != 2:
            raise ValueError("orjson only supports indent=2.")
        options |= orjson.OPT_INDENT_2  # type: ignore[union-attr]
    return options


def os_cpu_count() -> int | None:
    try:
        import os

        return os.cpu_count()
    except (ImportError, AttributeError):  # pragma: no cover - fallback
        return None


__all__ = ["JsonEmitConfig", "emit_json_samples"]
