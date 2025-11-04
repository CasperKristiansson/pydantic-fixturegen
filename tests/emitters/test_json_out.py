from __future__ import annotations

import datetime
import itertools
import json
from pathlib import Path

import pytest
from pydantic_fixturegen.core.path_template import OutputTemplate, OutputTemplateContext
from pydantic_fixturegen.emitters.json_out import emit_json_samples

try:
    import orjson  # type: ignore
except ImportError:  # pragma: no cover - optional dependency missing
    orjson = None  # type: ignore[assignment]


def test_emit_json_array_from_callable(tmp_path: Path) -> None:
    counter = itertools.count(1)

    def sample() -> dict[str, int]:
        return {"idx": next(counter)}

    output = tmp_path / "samples.json"
    paths = emit_json_samples(sample, output_path=output, count=3)

    assert paths == [output]
    content = json.loads(output.read_text(encoding="utf-8"))
    assert [item["idx"] for item in content] == [1, 2, 3]


def test_emit_jsonl_with_shards(tmp_path: Path) -> None:
    records = [{"item": i} for i in range(5)]
    base = tmp_path / "data.jsonl"

    paths = emit_json_samples(
        records,
        output_path=base,
        count=len(records),
        jsonl=True,
        shard_size=2,
    )

    assert len(paths) == 3
    assert paths[0].name.endswith("-00001.jsonl")
    assert paths[-1].name.endswith("-00003.jsonl")

    line_counts = [len(path.read_text(encoding="utf-8").splitlines()) for path in paths]
    assert line_counts == [2, 2, 1]


@pytest.mark.skipif(orjson is None, reason="orjson extra not installed")
def test_emit_json_with_orjson(tmp_path: Path) -> None:
    data = [{"message": "héllo"}]
    output = tmp_path / "orjson-output.json"

    paths = emit_json_samples(
        data,
        output_path=output,
        count=1,
        use_orjson=True,
        indent=2,
    )

    assert paths == [output]
    text = output.read_text(encoding="utf-8")
    assert "\n" in text  # indent ensures multi-line
    assert "héllo" in text
    loaded = json.loads(text)
    assert loaded == data


def test_emit_empty_output(tmp_path: Path) -> None:
    output = tmp_path / "empty-output.json"
    paths = emit_json_samples([], output_path=output, count=0)

    assert paths == [output]
    assert json.loads(output.read_text(encoding="utf-8")) == []


def test_emit_json_with_template(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "{model}" / "records-{case_index}")
    context = OutputTemplateContext(
        model="Widget",
        timestamp=datetime.datetime(2024, 7, 21, 14, 0, tzinfo=datetime.timezone.utc),
    )
    records = [{"idx": i} for i in range(3)]

    paths = emit_json_samples(
        records,
        output_path=template.raw,
        count=len(records),
        shard_size=1,
        template=template,
        template_context=context,
    )

    relative = [path.relative_to(tmp_path) for path in paths]
    assert relative == [
        Path("Widget/records-1.json"),
        Path("Widget/records-2.json"),
        Path("Widget/records-3.json"),
    ]
