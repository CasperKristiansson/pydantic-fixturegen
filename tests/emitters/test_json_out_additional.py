from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
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
