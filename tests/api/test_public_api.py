from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_fixturegen import api
from pydantic_fixturegen.api.models import ConfigSnapshot, JsonGenerationResult


def test_generate_json_type_annotation_sets_default_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_generate_json_artifacts(**kwargs: object) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(),
            base_output=tmp_path / "values.json",
            model=None,
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            constraint_summary=None,
            warnings=(),
            delegated=False,
        )

    monkeypatch.setattr(api, "generate_json_artifacts", fake_generate_json_artifacts)

    api.generate_json(
        target=None,
        out=tmp_path / "values.json",
        type_annotation=list[int],
    )

    assert captured["type_label"] == "list[int]"
