from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen.emitters.dataset_out import emit_dataset_samples


def _factory_generator(values: list[dict[str, object]]):
    items = values.copy()

    def _next() -> dict[str, object]:
        if not items:
            raise RuntimeError("exhausted test values")
        return items.pop(0)

    return _next


def test_emit_dataset_samples_csv(tmp_path: Path) -> None:
    factory = _factory_generator(
        [
            {"id": 1, "name": "alice", "__cycles__": []},
            {"id": 2, "name": "bob", "__cycles__": []},
        ]
    )

    paths = emit_dataset_samples(
        factory,
        output_path=tmp_path / "users",
        format="csv",
        count=2,
        columns=("id", "name", "__cycles__"),
    )

    assert len(paths) == 1
    content = paths[0].read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "id,name,__cycles__"
    assert content[1].startswith("1,alice,")
    assert content[2].startswith("2,bob,")


@pytest.mark.usefixtures("tmp_path")
def test_emit_dataset_samples_parquet(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    factory = _factory_generator(
        [
            {"id": 1, "name": "alice"},
            {"id": 2, "name": "bob"},
        ]
    )

    paths = emit_dataset_samples(
        factory,
        output_path=tmp_path / "users",
        format="parquet",
        count=2,
        columns=("id", "name", "__cycles__"),
    )

    assert len(paths) == 1
    table = pq.read_table(paths[0])
    assert table.num_rows == 2
    assert table.column("id").to_pylist() == [1, 2]


@pytest.mark.usefixtures("tmp_path")
def test_emit_dataset_samples_arrow(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    ipc = pytest.importorskip("pyarrow.ipc")

    factory = _factory_generator(
        [
            {"id": 1, "name": "alice"},
            {"id": 2, "name": "bob"},
        ]
    )

    paths = emit_dataset_samples(
        factory,
        output_path=tmp_path / "users",
        format="arrow",
        count=2,
        columns=("id", "name", "__cycles__"),
    )

    assert len(paths) == 1
    with ipc.open_file(paths[0]) as reader:
        table = reader.read_all()
    assert table.num_rows == 2
    assert table.column("name").to_pylist() == ["alice", "bob"]
