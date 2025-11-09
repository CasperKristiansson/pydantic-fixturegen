from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext
from pydantic_fixturegen.emitters import dataset_out as dataset


def _make_config(**overrides):
    return dataset.DatasetEmitConfig(
        output_path=overrides.get("output_path", Path("data")),
        template=overrides.get("template"),
        template_context=overrides.get("template_context"),
        format=overrides.get("format", "csv"),
        count=overrides.get("count", 4),
        shard_size=overrides.get("shard_size"),
        compression=overrides.get("compression"),
        columns=overrides.get("columns"),
    )


def test_normalise_format_and_compression_guards() -> None:
    assert dataset._normalise_format("CSV") == "csv"
    with pytest.raises(ValueError):
        dataset._normalise_format("xml")  # type: ignore[arg-type]

    assert dataset._normalise_csv_compression(None) is None
    assert dataset._normalise_csv_compression("GZIP") == "gzip"
    assert dataset._normalise_csv_compression("none") is None
    with pytest.raises(ValueError):
        dataset._normalise_csv_compression("brotli")


def test_parquet_and_arrow_compression_options() -> None:
    assert dataset._normalise_parquet_compression(None) == "snappy"
    assert dataset._normalise_parquet_compression("NONE") is None
    assert dataset._normalise_parquet_compression("zstd") == "zstd"
    with pytest.raises(ValueError):
        dataset._normalise_parquet_compression("weird")

    assert dataset._normalise_arrow_compression(None) == "zstd"
    assert dataset._normalise_arrow_compression("NONE") is None
    assert dataset._normalise_arrow_compression("lz4") == "lz4"
    with pytest.raises(ValueError):
        dataset._normalise_arrow_compression("gzip")


def test_apply_compression_suffix_and_shard_path(tmp_path: Path) -> None:
    config = _make_config(
        output_path=tmp_path / "dataset",
        shard_size=2,
        count=6,
        compression="gzip",
    )
    shard_path = dataset._render_shard_path(config, index=2, shard_total=3)
    assert shard_path.name.endswith(".csv.gz")
    assert "-00002" in shard_path.name


def test_render_shard_path_with_template(tmp_path: Path) -> None:
    template = OutputTemplate(str(tmp_path / "{case_index}" / "records"))
    config = _make_config(
        template=template,
        template_context=OutputTemplateContext(),
        output_path=tmp_path / "ignored",
        format="parquet",
    )
    rendered = dataset._render_shard_path(config, index=1, shard_total=1)
    assert rendered.parent.name == "1"
    assert rendered.suffix == ".parquet"


def test_consume_rows_and_iter_samples() -> None:
    iterator = iter([{"id": 1}])
    with pytest.raises(RuntimeError):
        list(dataset._consume_rows(iterator, 2))

    counter = {"calls": 0}

    def factory():
        counter["calls"] += 1
        return {"value": counter["calls"]}

    iterated = list(dataset._iter_samples(factory, 3))
    assert [entry["value"] for entry in iterated] == [1, 2, 3]

    iterable_iterated = list(dataset._iter_samples([{"value": 1}, {"value": 2}], 2))
    assert iterable_iterated[-1]["value"] == 2


def test_csv_cell_covers_supported_types() -> None:
    class Custom:
        def isoformat(self) -> str:
            return datetime(2024, 1, 1, 12, 0, 0).isoformat()

    assert dataset._csv_cell(None) == ""
    assert dataset._csv_cell(True) == "true"
    assert dataset._csv_cell(False) == "false"
    assert dataset._csv_cell(10) == 10
    assert dataset._csv_cell("hello") == "hello"
    assert dataset._csv_cell(Custom()).startswith("2024-01-01T12:00:00")
    assert dataset._csv_cell({"key": "value"}) == '{"key": "value"}'
