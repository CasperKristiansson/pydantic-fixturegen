from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.core import config_schema


def test_build_config_schema_contains_metadata() -> None:
    schema = config_schema.build_config_schema()

    assert schema["$schema"] == config_schema.SCHEMA_DRAFT
    assert schema["$id"] == config_schema.SCHEMA_ID
    assert schema["type"] == "object"
    assert "properties" in schema and "seed" in schema["properties"]


def test_packaged_schema_matches_generated(tmp_path: Path) -> None:
    packaged = Path("pydantic_fixturegen/schemas/config.schema.json").read_text(encoding="utf-8")
    generated = config_schema.get_config_schema_json()

    assert packaged == generated
