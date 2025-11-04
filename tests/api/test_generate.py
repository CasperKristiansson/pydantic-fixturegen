from __future__ import annotations

from pathlib import Path

import json

from pydantic_fixturegen.api import generate_fixtures, generate_json, generate_schema


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel, Field


class Address(BaseModel):
    city: str
    postcode: str = Field(min_length=3)


class User(BaseModel):
    name: str
    age: int
    address: Address


class Order(BaseModel):
    order_id: str
    total: float
""",
        encoding="utf-8",
    )
    return module_path


def test_generate_json_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_template = tmp_path / "artifacts" / "{model}" / "sample-{case_index}"

    result = generate_json(
        module_path,
        out=out_template,
        count=2,
        shard_size=1,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.model is not None and result.model.__name__ == "User"
    assert len(result.paths) == 2
    assert all(path.exists() for path in result.paths)
    records = [json.loads(path.read_text(encoding="utf-8")) for path in result.paths]
    assert len(records) == 2
    assert result.config.include == ("models.User",)


def test_generate_fixtures_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "fixtures" / "{model}" / "fixtures.py"

    result = generate_fixtures(
        module_path,
        out=output,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.path is not None and result.path.exists()
    text = result.path.read_text(encoding="utf-8")
    assert "def user(" in text
    assert not result.skipped


def test_generate_schema_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schemas" / "{model}" / "schema.json"

    result = generate_schema(
        module_path,
        out=output,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.path is not None and result.path.exists()
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["title"] == "User"
