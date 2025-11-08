"""Emitters for tabular dataset formats (CSV, Parquet, Arrow)."""

from __future__ import annotations

import csv
import gzip
import json
import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext

DatasetFormat = Literal["csv", "parquet", "arrow"]

_DEFAULT_BATCH_SIZE = 2048
_DEFAULT_SHARD_PAD = 5


@dataclass(slots=True)
class DatasetEmitConfig:
    output_path: Path
    template: OutputTemplate | None
    template_context: OutputTemplateContext | None
    format: DatasetFormat
    count: int
    shard_size: int | None
    compression: str | None
    columns: Sequence[str] | None


def emit_dataset_samples(
    samples: Iterable[Mapping[str, Any]] | Callable[[], Mapping[str, Any]],
    *,
    output_path: str | Path,
    format: DatasetFormat,
    count: int,
    shard_size: int | None = None,
    compression: str | None = None,
    template: OutputTemplate | None = None,
    template_context: OutputTemplateContext | None = None,
    columns: Sequence[str] | None = None,
) -> list[Path]:
    template_obj = template or OutputTemplate(output_path)
    context = template_context or OutputTemplateContext()
    resolved = template_obj.render(
        context=context,
        case_index=1 if template_obj.uses_case_index() else None,
    )

    config = DatasetEmitConfig(
        output_path=resolved,
        template=template_obj if template_obj.fields else None,
        template_context=context,
        format=_normalise_format(format),
        count=count,
        shard_size=shard_size if shard_size and shard_size > 0 else None,
        compression=compression,
        columns=tuple(columns or ()),
    )

    iterator = _iter_samples(samples, count)
    return _write_dataset(iterator, config)


def _write_dataset(iterator: Iterator[Mapping[str, Any]], config: DatasetEmitConfig) -> list[Path]:
    shard_size = config.shard_size or config.count
    shard_total = max(1, math.ceil(config.count / shard_size))
    emitted = 0
    results: list[Path] = []

    for index in range(1, shard_total + 1):
        rows_to_emit = min(shard_size, config.count - emitted)
        if rows_to_emit <= 0:
            break
        path = _render_shard_path(config, index=index, shard_total=shard_total)
        path.parent.mkdir(parents=True, exist_ok=True)
        if config.format == "csv":
            _write_csv_shard(iterator, rows_to_emit, path, config)
        elif config.format == "parquet":
            _write_parquet_shard(iterator, rows_to_emit, path, config)
        else:
            _write_arrow_shard(iterator, rows_to_emit, path, config)
        results.append(path)
        emitted += rows_to_emit

    return results


def _write_csv_shard(
    iterator: Iterator[Mapping[str, Any]],
    rows: int,
    path: Path,
    config: DatasetEmitConfig,
) -> None:
    columns = list(config.columns or [])
    if _normalise_csv_compression(config.compression) == "gzip":
        with gzip.open(path, mode="wt", encoding="utf-8", newline="\n") as stream:
            _write_csv_rows(stream, iterator, rows, columns)
    else:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            _write_csv_rows(stream, iterator, rows, columns)


def _write_csv_rows(
    stream: Any,
    iterator: Iterator[Mapping[str, Any]],
    rows: int,
    columns: list[str],
) -> None:
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    if columns:
        writer.writeheader()
    for row in _consume_rows(iterator, rows):
        if not columns:
            columns.extend(row.keys())
            writer.fieldnames = columns
            writer.writeheader()
        writer.writerow({col: _csv_cell(row.get(col)) for col in columns})


def _write_parquet_shard(
    iterator: Iterator[Mapping[str, Any]],
    rows: int,
    path: Path,
    config: DatasetEmitConfig,
) -> None:
    pa, pq = _require_pyarrow_parquet()
    compression = _normalise_parquet_compression(config.compression)
    writer: Any | None = None
    remaining = rows
    try:
        while remaining > 0:
            batch_count = min(_DEFAULT_BATCH_SIZE, remaining)
            records = list(_consume_rows(iterator, batch_count))
            remaining -= len(records)
            table = pa.Table.from_pylist(records) if records else None
            if writer is None:
                schema = table.schema if table is not None else _empty_schema(pa, config.columns)
                writer = pq.ParquetWriter(path, schema, compression=compression)
            if table is not None and table.num_rows:
                writer.write_table(table)
        if writer is None:
            schema = _empty_schema(pa, config.columns)
            writer = pq.ParquetWriter(path, schema, compression=compression)
    finally:
        if writer is not None:
            writer.close()


def _write_arrow_shard(
    iterator: Iterator[Mapping[str, Any]],
    rows: int,
    path: Path,
    config: DatasetEmitConfig,
) -> None:
    pa, ipc = _require_pyarrow_ipc()
    compression = _normalise_arrow_compression(config.compression)
    remaining = rows
    writer: Any | None = None
    schema = None
    options = ipc.IpcWriteOptions(compression=compression)
    try:
        while remaining > 0:
            batch_count = min(_DEFAULT_BATCH_SIZE, remaining)
            records = list(_consume_rows(iterator, batch_count))
            remaining -= len(records)
            table = pa.Table.from_pylist(records) if records else None
            if writer is None:
                schema = table.schema if table is not None else _empty_schema(pa, config.columns)
                writer = ipc.new_file(path, schema=schema, options=options)
            if table is not None and table.num_rows:
                writer.write_table(table)
        if writer is None:
            schema = _empty_schema(pa, config.columns)
            with ipc.new_file(path, schema=schema, options=options):
                pass
    finally:
        if writer is not None:
            writer.close()


def _consume_rows(iterator: Iterator[Mapping[str, Any]], limit: int) -> Iterator[Mapping[str, Any]]:
    consumed = 0
    while consumed < limit:
        try:
            row = next(iterator)
        except StopIteration as exc:
            raise RuntimeError("Insufficient samples produced for requested count.") from exc
        consumed += 1
        yield row


def _iter_samples(
    source: Iterable[Mapping[str, Any]] | Callable[[], Mapping[str, Any]],
    count: int,
) -> Iterator[Mapping[str, Any]]:
    if callable(source):
        for _ in range(count):
            yield source()
        return

    iterator = iter(source)
    for _ in range(count):
        try:
            yield next(iterator)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise RuntimeError("Sample iterable ended before count was satisfied.") from exc


def _render_shard_path(config: DatasetEmitConfig, *, index: int, shard_total: int) -> Path:
    suffix = _format_suffix(config.format)
    template = config.template
    if template is None:
        base_path = config.output_path
    else:
        base_path = template.render(
            context=config.template_context,
            case_index=index if template.uses_case_index() else None,
        )
    if (template is not None and template.uses_case_index()) or shard_total <= 1:
        path = _ensure_suffix(base_path, suffix)
    else:
        path = _shard_path(base_path, index, shard_total, suffix)
    return _apply_compression_suffix(path, config.format, config.compression)


def _format_suffix(fmt: DatasetFormat) -> str:
    if fmt == "csv":
        return ".csv"
    if fmt == "parquet":
        return ".parquet"
    return ".arrow"


def _ensure_suffix(path: Path, suffix: str) -> Path:
    if path.suffix:
        return path.with_suffix(suffix)
    return path.with_name(f"{path.name}{suffix}")


def _shard_path(base_path: Path, shard_index: int, shard_total: int, suffix: str) -> Path:
    if shard_total <= 1:
        return _ensure_suffix(base_path, suffix)
    stem = base_path.stem or base_path.name
    parent = base_path.parent
    return parent / f"{stem}-{shard_index:0{_DEFAULT_SHARD_PAD}d}{suffix}"


def _apply_compression_suffix(path: Path, fmt: DatasetFormat, compression: str | None) -> Path:
    if fmt != "csv":
        return path
    if _normalise_csv_compression(compression) == "gzip" and path.suffix != ".gz":
        return Path(f"{path}.gz")
    return path


def _normalise_format(format_value: DatasetFormat) -> DatasetFormat:
    value = format_value.lower()
    if value not in {"csv", "parquet", "arrow"}:
        raise ValueError(f"Unsupported dataset format: {format_value}")
    return cast(DatasetFormat, value)


def _normalise_csv_compression(compression: str | None) -> str | None:
    if compression is None:
        return None
    value = compression.lower()
    if value not in {"gzip", "none"}:
        raise ValueError("CSV compression must be 'gzip' or 'none'.")
    return None if value == "none" else value


def _normalise_parquet_compression(compression: str | None) -> str | None:
    if compression is None:
        return "snappy"
    value = compression.lower()
    if value == "none":
        return None
    allowed = {"snappy", "gzip", "brotli", "zstd", "lz4"}
    if value not in allowed:
        raise ValueError("Unsupported Parquet compression.")
    return value


def _normalise_arrow_compression(compression: str | None) -> str | None:
    if compression is None:
        return "zstd"
    value = compression.lower()
    if value == "none":
        return None
    allowed = {"zstd", "lz4"}
    if value not in allowed:
        raise ValueError("Unsupported Arrow compression.")
    return value


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - defensive
            pass
    return json.dumps(value, ensure_ascii=False)


def _empty_schema(pa_module: Any, columns: Sequence[str] | None) -> Any:
    fields = []
    for name in columns or ():
        fields.append(pa_module.field(name, pa_module.null()))
    return pa_module.schema(fields)


def _require_pyarrow_parquet() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("pyarrow is required for Parquet emission.") from exc
    return pa, pq


def _require_pyarrow_ipc() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.ipc as ipc
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("pyarrow is required for Arrow emission.") from exc
    return pa, ipc


__all__ = ["DatasetFormat", "emit_dataset_samples"]
