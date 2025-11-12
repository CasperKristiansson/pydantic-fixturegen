"""Utilities for emitting generated instances to JSON/JSONL files."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, is_dataclass
from itertools import islice
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from pydantic import BaseModel

from pydantic_fixturegen.core.cycle_report import consume_cycle_events
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext

orjson: ModuleType | None
try:  # Optional dependency
    import orjson as _orjson
except ImportError:  # pragma: no cover - optional extra not installed
    orjson = None
else:
    orjson = _orjson

DEFAULT_INDENT = 2
DEFAULT_SHARD_PAD = 5


@dataclass(slots=True)
class JsonEmitConfig:
    """Configuration options for JSON emission."""

    output_path: Path
    count: int
    template: OutputTemplate | None = None
    template_context: OutputTemplateContext | None = None
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
    template: OutputTemplate | None = None,
    template_context: OutputTemplateContext | None = None,
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

    template_obj = template or OutputTemplate(output_path)
    context = template_context or OutputTemplateContext()

    if template_obj.fields:
        initial_index = 1 if template_obj.uses_case_index() else None
        resolved_path = template_obj.render(context=context, case_index=initial_index)
    else:
        resolved_path = template_obj.render(context=context)

    config = JsonEmitConfig(
        output_path=resolved_path,
        count=count,
        template=template_obj if template_obj.fields else None,
        template_context=context,
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

    samples_iter = _collect_samples(samples, config.count)

    if config.shard_size is None:
        if config.jsonl:
            path = _stream_jsonl(
                samples_iter,
                _resolve_base_path(config, index=1),
                encoder,
            )
        else:
            path = _stream_json_array(
                samples_iter,
                _resolve_base_path(config, index=1),
                encoder,
                indent=config.indent,
            )
        return [path]

    return _write_chunked_samples(samples_iter, config, encoder)


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
        for yielded, item in enumerate(samples):
            if yielded >= count:
                break
            yield _normalise_record(item)

    return iterable_iterator()


def _normalise_indent(indent: int | None, *, jsonl: bool) -> int | None:
    if jsonl:
        return None
    if indent is None or indent == 0:
        return None
    if indent < 0:
        raise ValueError("indent must be >= 0")
    return indent


def _normalise_shard_size(shard_size: int | None, count: int) -> int | None:
    if shard_size is None or shard_size <= 0:
        return None
    return max(1, min(shard_size, count)) if count > 0 else shard_size


def _worker_count(max_workers: int | None, shard_count: int) -> int:
    if shard_count <= 1:
        return 1
    if max_workers is not None:
        return max(1, min(max_workers, shard_count))
    return min(shard_count, (os_cpu_count() or 1) * 2)


def _write_empty_shard(
    base_path: Path,
    jsonl: bool,
    encoder: _JsonEncoder,
) -> Path:
    path = _shard_path(base_path, 1, 1, jsonl)
    empty_payload = "" if jsonl else encoder.encode([])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(empty_payload, encoding="utf-8", newline="\n")
    return path


def _prepare_payload(
    chunk: Sequence[Any],
    *,
    jsonl: bool,
    encoder: _JsonEncoder,
    workers: int,
) -> str:
    if not jsonl:
        payload = encoder.encode(list(chunk))
        if payload and not payload.endswith("\n"):
            payload += "\n"
        return payload

    if workers <= 1:
        lines = [encoder.encode(item) for item in chunk]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            lines = list(executor.map(encoder.encode, chunk))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _stream_jsonl(
    iterator: Iterator[Any],
    base_path: Path,
    encoder: _JsonEncoder,
) -> Path:
    path = _ensure_suffix(base_path, ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in iterator:
            stream.write(encoder.encode(record))
            stream.write("\n")
    return path


def _stream_json_array(
    iterator: Iterator[Any],
    base_path: Path,
    encoder: _JsonEncoder,
    *,
    indent: int | None,
) -> Path:
    path = _ensure_suffix(base_path, ".json")
    path.parent.mkdir(parents=True, exist_ok=True)

    if indent is None:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            first = True
            stream.write("[")
            for record in iterator:
                if not first:
                    stream.write(",")
                stream.write(encoder.encode(record))
                first = False
            stream.write("]\n")
        return path

    spacing = " " * indent
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        written = False
        for record in iterator:
            encoded = encoder.encode(record)
            if not written:
                stream.write("[\n")
            else:
                stream.write(",\n")
            stream.write(f"{spacing}{encoded}")
            written = True
        if not written:
            stream.write("[]\n")
        else:
            stream.write("\n]\n")
    return path


def _write_chunked_samples(
    iterator: Iterator[Any],
    config: JsonEmitConfig,
    encoder: _JsonEncoder,
) -> list[Path]:
    chunk_size = max(1, config.shard_size or 1)
    results: list[Path] = []

    chunk = list(islice(iterator, chunk_size))
    if not chunk:
        results.append(
            _write_empty_shard(
                _resolve_base_path(config, index=1),
                config.jsonl,
                encoder,
            )
        )
        return results

    index = 1
    while chunk:
        next_chunk = list(islice(iterator, chunk_size))
        is_last = not next_chunk
        path = _chunk_path(
            config,
            index=index,
            is_last=is_last,
            jsonl=config.jsonl,
        )
        payload = _prepare_payload(
            chunk,
            jsonl=config.jsonl,
            encoder=encoder,
            workers=_worker_count(config.max_workers, len(chunk)),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8", newline="\n")
        results.append(path)

        chunk = next_chunk
        index += 1

    return results


def _chunk_path(
    config: JsonEmitConfig,
    *,
    index: int,
    is_last: bool,
    jsonl: bool,
) -> Path:
    template = config.template
    if template is not None:
        base_path = template.render(
            context=config.template_context,
            case_index=index if template.uses_case_index() else None,
        )
    else:
        base_path = config.output_path

    suffix = ".jsonl" if jsonl else ".json"
    if template is not None and template.uses_case_index():
        return _ensure_suffix(base_path, suffix)
    if is_last and index == 1:
        return _ensure_suffix(base_path, suffix)

    shard_total = 2 if (index > 1 or not is_last) else 1
    return _shard_path(base_path, index, shard_total, jsonl)


def _resolve_base_path(config: JsonEmitConfig, *, index: int) -> Path:
    template = config.template
    if template is None:
        return config.output_path
    return template.render(
        context=config.template_context,
        case_index=index if template.uses_case_index() else None,
    )


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
    if bool(is_dataclass(record)):
        if isinstance(record, type):
            return record
        payload = asdict(record)
        events = consume_cycle_events(record)
        if events:
            payload["__cycles__"] = [event.to_payload() for event in events]
        return payload
    if isinstance(record, BaseModel):
        data = record.model_dump()
        events = consume_cycle_events(record)
        if events:
            data["__cycles__"] = [event.to_payload() for event in events]
        return data
    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        dump_call = cast(Callable[[], Any], model_dump)
        payload = dump_call()
        events = consume_cycle_events(record)
        if events and isinstance(payload, dict):
            payload = dict(payload)
            payload["__cycles__"] = [event.to_payload() for event in events]
        return payload
    return record


class _JsonEncoder:
    def __init__(self, *, indent: int | None, ensure_ascii: bool, use_orjson: bool) -> None:
        self.indent = indent
        self.ensure_ascii = ensure_ascii
        self.use_orjson = use_orjson
        self._options: int | None = None
        if use_orjson:
            if orjson is None:
                raise RuntimeError("orjson is not installed but use_orjson was requested.")
            self._options = _orjson_options(indent)

    def encode(self, obj: Any) -> str:
        normalized = _normalise_record(obj)
        if self.use_orjson:
            assert orjson is not None  # for type checkers
            options = self._options if self._options is not None else 0
            bytes_payload = orjson.dumps(normalized, option=options)
            return cast(bytes, bytes_payload).decode("utf-8")
        return json.dumps(
            normalized,
            ensure_ascii=self.ensure_ascii,
            indent=self.indent,
            sort_keys=True,
        )


def _orjson_options(indent: int | None) -> int:
    if orjson is None:  # pragma: no cover - defensive
        raise RuntimeError("orjson is not available")
    options = cast(int, orjson.OPT_SORT_KEYS)
    if indent:
        if indent != 2:
            raise ValueError("orjson only supports indent=2.")
        options |= cast(int, orjson.OPT_INDENT_2)
    return options


def os_cpu_count() -> int | None:
    try:
        import os

        return os.cpu_count()
    except (ImportError, AttributeError):  # pragma: no cover - fallback
        return None


__all__ = ["JsonEmitConfig", "emit_json_samples"]
