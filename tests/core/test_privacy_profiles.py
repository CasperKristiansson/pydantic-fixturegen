from __future__ import annotations

import pytest
from pydantic_fixturegen.core.privacy_profiles import (
    available_privacy_profiles,
    get_privacy_profile_spec,
    normalize_privacy_profile_name,
)


def test_normalize_privacy_profile_name_aliases() -> None:
    assert normalize_privacy_profile_name(" SAFE ") == "pii-safe"
    assert normalize_privacy_profile_name("Prod") == "realistic"
    assert normalize_privacy_profile_name("edge-case") == "edge"
    assert normalize_privacy_profile_name("CHAOS") == "adversarial"


def test_get_privacy_profile_spec_and_available() -> None:
    spec = get_privacy_profile_spec("prod")
    assert spec.name == "realistic"
    profiles = available_privacy_profiles()
    assert spec in profiles

    with pytest.raises(KeyError):
        get_privacy_profile_spec("unknown-profile")


def test_edge_profile_configuration() -> None:
    spec = get_privacy_profile_spec("edge")
    assert spec.settings["numbers"]["distribution"] == "spike"
    assert spec.settings["union_policy"] == "random"


def test_adversarial_profile_configuration() -> None:
    spec = get_privacy_profile_spec("adversarial")
    arrays = spec.settings["arrays"]
    assert arrays["max_elements"] == 2
    assert spec.settings["p_none"] > 0.5
