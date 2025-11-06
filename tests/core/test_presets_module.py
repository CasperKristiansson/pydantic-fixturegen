from __future__ import annotations

import pytest
from pydantic_fixturegen.core import presets


def test_normalize_preset_name_handles_aliases() -> None:
    assert presets.normalize_preset_name("Boundary") == "boundary"
    assert presets.normalize_preset_name(" boundary-heavy ") == "boundary-max"


def test_get_preset_spec_returns_expected_values() -> None:
    spec = presets.get_preset_spec("boundary")

    assert spec.name == "boundary"
    assert spec.settings["union_policy"] == "random"
    assert spec.settings["p_none"] == pytest.approx(0.35)


def test_available_presets_contains_alias_targets() -> None:
    available = presets.available_presets()
    names = {spec.name for spec in available}

    assert {"boundary", "boundary-max"} <= names
