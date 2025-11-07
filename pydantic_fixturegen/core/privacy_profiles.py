"""Privacy profile definitions for privacy-aware generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PrivacyProfileSpec:
    """Descriptor for a privacy profile and the config overrides it applies."""

    name: str
    description: str
    settings: Mapping[str, Any]


_PROFILE_DEFINITIONS: dict[str, PrivacyProfileSpec] = {
    "pii-safe": PrivacyProfileSpec(
        name="pii-safe",
        description=(
            "Mask identifier providers and prefer None for optional PII fields."
            " Ensures generated credentials stay inside reserved example domains."
        ),
        settings={
            "identifiers": {
                "mask_sensitive": True,
                "url_include_path": False,
                "url_schemes": ["https"],
            },
            "field_policies": {
                "*.email": {"p_none": 0.65},
                "*.Email": {"p_none": 0.65},
                "*.phone*": {"p_none": 0.5},
                "*.Phone*": {"p_none": 0.5},
                "*.ssn": {"p_none": 0.9},
                "*.tax_id": {"p_none": 0.9},
                "*.TaxId": {"p_none": 0.9},
            },
        },
    ),
    "realistic": PrivacyProfileSpec(
        name="realistic",
        description=(
            "Favor realistic identifier distributions and keep optional contact fields populated."
        ),
        settings={
            "identifiers": {
                "mask_sensitive": False,
                "url_include_path": True,
                "url_schemes": ["https", "http"],
            },
            "field_policies": {
                "*.email": {"p_none": 0.05},
                "*.phone*": {"p_none": 0.1},
            },
        },
    ),
}

_ALIASES: dict[str, str] = {
    "safe": "pii-safe",
    "pii": "pii-safe",
    "prod": "realistic",
}


def normalize_privacy_profile_name(name: str) -> str:
    """Normalize a privacy profile name applying aliases and case folding."""

    key = name.strip().lower()
    return _ALIASES.get(key, key)


def get_privacy_profile_spec(name: str) -> PrivacyProfileSpec:
    """Return the profile specification for ``name`` or raise ``KeyError``."""

    normalized = normalize_privacy_profile_name(name)
    return _PROFILE_DEFINITIONS[normalized]


def available_privacy_profiles() -> list[PrivacyProfileSpec]:
    """Return all available privacy profile specifications."""

    return list(_PROFILE_DEFINITIONS.values())


__all__ = [
    "PrivacyProfileSpec",
    "available_privacy_profiles",
    "get_privacy_profile_spec",
    "normalize_privacy_profile_name",
]
