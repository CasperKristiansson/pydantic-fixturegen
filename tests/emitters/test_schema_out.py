from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.core.path_template import (
    OutputTemplate,
    OutputTemplateContext,
    OutputTemplateError,
)
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema


class User(BaseModel):
    id: int
    name: str


class Account(BaseModel):
    z: int
    a: int


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
    path = emit_models_schema([Account, User], output_path=output, indent=None)

    assert path == output
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    payload = json.loads(text)
    assert list(payload) == ["Account", "User"]


def test_emit_schema_compact(tmp_path: Path) -> None:
    output = tmp_path / "compact.json"
    path = emit_model_schema(User, output_path=output, indent=0)

    assert path == output
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "\n" not in text[:-1]


def test_emit_model_schema_with_template(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "{model}" / "schema-{timestamp}.json")
    context = OutputTemplateContext(
        model="User",
        timestamp=datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.timezone.utc),
    )

    path = emit_model_schema(
        User,
        output_path=template.raw,
        template=template,
        template_context=context,
    )

    assert path.parent.name == "User"
    assert path.name.startswith("schema-20240101")
    assert path.suffix == ".json"


def test_emit_models_schema_template_requires_model(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "{model}" / "bundle.json")

    with pytest.raises(OutputTemplateError):
        emit_models_schema(
            [Account, User],
            output_path=template.raw,
            template=template,
            template_context=OutputTemplateContext(
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            ),
        )
