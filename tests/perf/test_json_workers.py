from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.emitters.json_out import emit_json_samples


def test_jsonl_parallel_workers(tmp_path: Path) -> None:
    serial = tmp_path / "serial.jsonl"
    emit_json_samples(
        range(50),
        output_path=serial,
        count=50,
        jsonl=True,
        max_workers=1,
    )

    parallel = tmp_path / "parallel.jsonl"
    emit_json_samples(
        range(50),
        output_path=parallel,
        count=50,
        jsonl=True,
        max_workers=4,
    )

    assert parallel.read_text(encoding="utf-8") == serial.read_text(encoding="utf-8")


def test_json_parallel_workers(tmp_path: Path) -> None:
    serial = tmp_path / "serial.json"
    emit_json_samples(
        range(20),
        output_path=serial,
        count=20,
        max_workers=1,
    )

    parallel = tmp_path / "parallel.json"
    emit_json_samples(
        range(20),
        output_path=parallel,
        count=20,
        max_workers=4,
    )

    assert parallel.read_text(encoding="utf-8") == serial.read_text(encoding="utf-8")
