from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.core.config_schema import (
    SCHEMA_DRAFT,
    SCHEMA_ID,
    build_config_schema,
    get_config_schema_json,
)


def test_build_config_schema_contains_metadata() -> None:
    schema = build_config_schema()

    assert schema["$schema"] == SCHEMA_DRAFT
    assert schema["$id"] == SCHEMA_ID
    assert schema["type"] == "object"
    assert "properties" in schema and "seed" in schema["properties"]


def test_packaged_schema_matches_generated(tmp_path: Path) -> None:
    packaged = Path("pydantic_fixturegen/schemas/config.schema.json").read_text(encoding="utf-8")
    generated = get_config_schema_json()

    assert packaged == generated
