from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.cli.anonymize import (
    FileMeta,
    _collect_input_files,
    _doctor_gap_summary,
    _read_records,
    _resolve_output_path,
    _write_records,
)
from pydantic_fixturegen.core.errors import EmitError


def test_collect_input_files_behaviour(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "a.json").write_text("[]", encoding="utf-8")
    (nested / "b.jsonl").write_text("{}", encoding="utf-8")
    files = _collect_input_files(tmp_path)
    assert len(files) == 2
    assert files[0].name == "a.json"
    with pytest.raises(EmitError):
        _collect_input_files(tmp_path / "missing.json")


def test_read_and_write_records_json_variants(tmp_path: Path) -> None:
    json_file = tmp_path / "single.json"
    json_file.write_text(json.dumps({"email": "one"}), encoding="utf-8")
    json_records, json_meta = _read_records(json_file)
    assert json_meta.single_object is True
    assert json_records[0]["email"] == "one"

    jsonl_file = tmp_path / "multi.jsonl"
    jsonl_file.write_text('{"value": 1}\n{"value": 2}\n', encoding="utf-8")
    jsonl_records, jsonl_meta = _read_records(jsonl_file)
    assert len(jsonl_records) == 2
    assert jsonl_meta.format == "jsonl"

    outfile = tmp_path / "out.jsonl"
    _write_records(jsonl_records, jsonl_meta, outfile)
    assert outfile.read_text(encoding="utf-8").count("\n") == 2

    single_out = tmp_path / "single_out.json"
    _write_records(json_records, json_meta, single_out)
    assert json.loads(single_out.read_text(encoding="utf-8"))["email"] == "one"


def test_resolve_output_path(tmp_path: Path) -> None:
    input_file = tmp_path / "data.json"
    input_file.write_text("[]", encoding="utf-8")
    output_dir = tmp_path / "out"
    resolved = _resolve_output_path(
        input_path=input_file,
        input_root=input_file,
        output=output_dir,
        output_is_dir=True,
        meta=FileMeta(path=input_file, format="json", single_object=False),
    )
    assert resolved.parent == output_dir


def test_doctor_gap_summary(tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Entry(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    summary = _doctor_gap_summary(
        module,
        include=None,
        exclude=None,
        timeout=1.0,
        memory_limit_mb=64,
    )
    assert "total_error_fields" in summary
