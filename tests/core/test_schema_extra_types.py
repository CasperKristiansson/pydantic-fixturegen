from __future__ import annotations

from pydantic_extra_types.color import Color
from pydantic_extra_types.coordinate import Coordinate
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.extra_types import (
    available_type_ids,
    describe_extra_annotation,
    is_extra_annotation,
    iter_available_types,
    resolve_type_id,
)
from pydantic_fixturegen.core.schema import FieldConstraints


def test_summarize_color_annotation() -> None:
    summary = schema_module._summarize_annotation(Color, FieldConstraints())
    assert summary.type == "color"


def test_describe_extra_annotation_for_color() -> None:
    label = describe_extra_annotation(Color)
    assert label is not None
    assert label.endswith("color.Color")


def test_summarize_coordinate_annotation() -> None:
    summary = schema_module._summarize_annotation(Coordinate, FieldConstraints())
    assert summary.type == "coordinate"


def test_extra_type_helpers_expose_registry() -> None:
    mapping = iter_available_types()
    assert set(mapping).issubset(set(available_type_ids()))


def test_resolve_type_id_non_type_returns_none() -> None:
    assert resolve_type_id("not-a-type") is None


def test_describe_extra_annotation_handles_wrapped_type() -> None:
    label = describe_extra_annotation(list[Color])
    assert isinstance(label, str)
    assert label.endswith("color.Color")


def test_is_extra_annotation_matches_color() -> None:
    assert is_extra_annotation(Color) is True
