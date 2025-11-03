"""Preset definitions for curated generation policy bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PresetSpec:
    """Descriptor for a preset and the configuration values it applies."""

    name: str
    description: str
    settings: Mapping[str, Any]


_PRESET_DEFINITIONS: dict[str, PresetSpec] = {
    "boundary": PresetSpec(
        name="boundary",
        description=(
            "Favor random union/enum selection and increase optional None probability for"
            " boundary-focused datasets."
        ),
        settings={
            "union_policy": "random",
            "enum_policy": "random",
            "p_none": 0.35,
        },
    ),
    "boundary-max": PresetSpec(
        name="boundary-max",
        description=(
            "Aggressive boundary exploration with high optional None probability and"
            " randomized union/enum selection."
        ),
        settings={
            "union_policy": "random",
            "enum_policy": "random",
            "p_none": 0.6,
            "json": {"indent": 0},
        },
    ),
}

_ALIASES: dict[str, str] = {
    "edge": "boundary",
    "boundary-heavy": "boundary-max",
}


def normalize_preset_name(name: str) -> str:
    """Normalize a preset name applying aliases and case folding."""

    key = name.strip().lower()
    return _ALIASES.get(key, key)


def get_preset_spec(name: str) -> PresetSpec:
    """Return the preset specification for ``name`` or raise ``KeyError``."""

    normalized = normalize_preset_name(name)
    return _PRESET_DEFINITIONS[normalized]


def available_presets() -> list[PresetSpec]:
    """Return the list of available preset specifications."""

    return list(_PRESET_DEFINITIONS.values())


__all__ = ["PresetSpec", "available_presets", "get_preset_spec", "normalize_preset_name"]
