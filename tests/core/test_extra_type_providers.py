from __future__ import annotations

import random

import pytest
from faker import Faker

from pydantic_fixturegen.core.providers import extra_types as extra_mod
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


@pytest.fixture()
def field_summary() -> FieldSummary:
    return FieldSummary(type="string", constraints=FieldConstraints())


def test_register_extra_type_providers_filters_available(monkeypatch: pytest.MonkeyPatch, field_summary: FieldSummary) -> None:
    monkeypatch.setattr(extra_mod, "available_type_ids", lambda: {"color", "ulid"})
    registry = ProviderRegistry()
    extra_mod.register_extra_type_providers(registry)

    color_provider = registry.get("color")
    ulid_provider = registry.get("ulid")
    assert color_provider is not None
    assert ulid_provider is not None

    rng = random.Random(0)
    value = color_provider.func(field_summary, random_generator=rng)
    assert value.startswith("#")
    assert len(ulid_provider.func(field_summary, random_generator=rng)) == 26


@pytest.mark.parametrize("type_id", sorted(extra_mod._EXTRA_GENERATORS.keys()))
def test_extra_generators_produce_values(type_id: str, field_summary: FieldSummary) -> None:
    rng = random.Random(0)
    faker = Faker()
    generator = extra_mod._EXTRA_GENERATORS[type_id]
    value = generator(field_summary, random_generator=rng, faker=faker)
    assert value is not None
    if type_id == "coordinate":
        lat, lon = value
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
    elif type_id in {"epoch-number", "epoch-integer", "latitude", "longitude"}:
        assert isinstance(value, (int, float))
    else:
        assert isinstance(value, (str, tuple))
