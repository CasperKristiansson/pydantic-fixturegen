from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema


class User(BaseModel):
    id: int
    name: str


@dataclass
class Profile:
    active: bool


def test_emit_single_model_schema(tmp_path: Path) -> None:
    output = tmp_path / "user-schema.json"
    path = emit_model_schema(User, output_path=output, indent=2)

    assert path == output
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["title"] == "User"
    assert payload["properties"]["name"]["type"] == "string"


def test_emit_multiple_models_schema(tmp_path: Path) -> None:
    output = tmp_path / "bundle.json"
    path = emit_models_schema([User], output_path=output, indent=None)

    assert path == output
    text = path.read_text(encoding="utf-8")
    assert "User" in text
    payload = json.loads(text)
    assert list(payload) == ["User"]


def test_emit_schema_compact(tmp_path: Path) -> None:
    output = tmp_path / "compact.json"
    path = emit_model_schema(User, output_path=output, indent=0)

    assert path == output
    text = path.read_text(encoding="utf-8")
    assert "\n" not in text
