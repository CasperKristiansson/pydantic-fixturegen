from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.emitters import json_out


def test_emit_json_samples_empty(tmp_path: Path) -> None:
    output = tmp_path / "empty.jsonl"
    paths = json_out.emit_json_samples(
        [],
        output_path=output,
        count=0,
        jsonl=True,
    )
    assert paths[0].read_text(encoding="utf-8") == ""


def test_emit_json_samples_jsonl_threadpool(tmp_path: Path) -> None:
    output = tmp_path / "sharded.jsonl"

    def factory() -> dict[str, int]:
        return {"value": 1}

    paths = json_out.emit_json_samples(
        factory,
        output_path=output,
        count=5,
        jsonl=True,
        shard_size=2,
        max_workers=4,
    )

    assert len(paths) == 3
    assert all(path.read_text(encoding="utf-8").strip() for path in paths[:-1])


def test_emit_json_samples_appends_newline_and_sorts_keys(tmp_path: Path) -> None:
    output = tmp_path / "data.json"
    payload = [{"z": 1, "a": 2}]

    paths = json_out.emit_json_samples(payload, output_path=output, count=1, jsonl=False)

    text = paths[0].read_text(encoding="utf-8")
    assert text.endswith("\n")
    decoded = json.loads(text)
    assert isinstance(decoded, list)
    assert list(decoded[0]) == ["a", "z"]


def test_emit_json_samples_jsonl_trailing_newline(tmp_path: Path) -> None:
    output = tmp_path / "data.jsonl"

    paths = json_out.emit_json_samples([{"b": 2, "a": 1}], output_path=output, count=1, jsonl=True)

    text = paths[0].read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert list(json.loads(text.strip()).keys()) == ["a", "b"]


def test_json_encoder_orjson(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyOrjson:
        OPT_SORT_KEYS = 1
        OPT_INDENT_2 = 2

        @staticmethod
        def dumps(obj: object, option: int) -> bytes:  # noqa: ANN401
            return json.dumps(obj, sort_keys=bool(option & 1)).encode("utf-8")

    monkeypatch.setattr(json_out, "orjson", DummyOrjson)
    encoder = json_out._JsonEncoder(indent=2, ensure_ascii=False, use_orjson=True)
    assert encoder.encode({"b": 1, "a": 2}).startswith("{")


def test_orjson_options_invalid_indent(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyOrjson:
        OPT_SORT_KEYS = 1
        OPT_INDENT_2 = 2

        @staticmethod
        def dumps(obj: object, option: int) -> bytes:  # pragma: no cover
            return b"{}"

    monkeypatch.setattr(json_out, "orjson", DummyOrjson)
    with pytest.raises(ValueError):
        json_out._orjson_options(4)


def test_normalise_record_dataclass_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclasses.dataclass
    class Example:
        value: int

    class Model:
        def model_dump(self) -> dict[str, int]:
            return {"value": 5}

    assert json_out._normalise_record(Example(1)) == {"value": 1}
    assert json_out._normalise_record(Model()) == {"value": 5}


def test_normalise_indent_negative() -> None:
    with pytest.raises(ValueError):
        json_out._normalise_indent(-1, jsonl=False)


def test_collect_samples_limits_iterables() -> None:
    iterator = json_out._collect_samples([1, 2, 3], count=1)
    assert list(iterator) == [1]


def test_write_empty_shard_emits_placeholder(tmp_path: Path) -> None:
    encoder = json_out._JsonEncoder(indent=None, ensure_ascii=True, use_orjson=False)
    path = json_out._write_empty_shard(tmp_path / "payload", jsonl=False, encoder=encoder)
    assert path.read_text(encoding="utf-8") == "[]"


def test_prepare_payload_handles_empty_jsonl() -> None:
    encoder = json_out._JsonEncoder(indent=None, ensure_ascii=False, use_orjson=False)
    payload = json_out._prepare_payload([], jsonl=True, encoder=encoder, workers=1)
    assert payload == ""


def test_write_chunked_samples_writes_empty_shard(tmp_path: Path) -> None:
    encoder = json_out._JsonEncoder(indent=None, ensure_ascii=False, use_orjson=False)
    config = json_out.JsonEmitConfig(
        output_path=tmp_path / "data",
        count=0,
        shard_size=5,
        jsonl=False,
    )
    paths = json_out._write_chunked_samples(iter(()), config, encoder)
    assert len(paths) == 1
    assert paths[0].read_text(encoding="utf-8") == "[]"


def test_chunk_path_prefers_single_file(tmp_path: Path) -> None:
    config = json_out.JsonEmitConfig(output_path=tmp_path / "data", count=1)
    path = json_out._chunk_path(config, index=1, is_last=True, jsonl=False)
    assert path.suffix == ".json"


def test_shard_path_single_shard(tmp_path: Path) -> None:
    base = tmp_path / "items"
    path = json_out._shard_path(base, shard_index=1, shard_count=1, jsonl=True)
    assert path.suffix == ".jsonl"


def test_normalise_record_includes_cycle_events(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyEvent:
        def to_payload(self) -> dict[str, str]:
            return {"path": "root"}

    monkeypatch.setattr(json_out, "consume_cycle_events", lambda _: [DummyEvent()])

    @dataclasses.dataclass
    class Example:
        value: int

    class Model(BaseModel):
        value: int = 7

    class Custom:
        def model_dump(self) -> dict[str, str]:
            return {"value": "ok"}

    assert "__cycles__" in json_out._normalise_record(Example(1))
    assert "__cycles__" in json_out._normalise_record(Model())
    assert "__cycles__" in json_out._normalise_record(Custom())


def test_json_encoder_requires_orjson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(json_out, "orjson", None)
    with pytest.raises(RuntimeError):
        json_out._JsonEncoder(indent=None, ensure_ascii=False, use_orjson=True)


def test_json_fallback_uses_str() -> None:
    class Example:
        def __str__(self) -> str:
            return "example"

    assert json_out._json_fallback(Example()) == "example"
