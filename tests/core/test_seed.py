from __future__ import annotations

import random

import numpy as np
import pytest
from pydantic_fixturegen.core.seed import PortableRandom, SeedManager


def test_base_random_repeatable() -> None:
    manager_a = SeedManager(seed=1234)
    manager_b = SeedManager(seed=1234)

    sequence_a = [manager_a.base_random.random() for _ in range(3)]
    sequence_b = [manager_b.base_random.random() for _ in range(3)]

    assert sequence_a == sequence_b


def test_portable_rng_sequence_is_stable() -> None:
    manager = SeedManager(seed=1234, rng_mode="portable")

    values = [manager.base_random.random() for _ in range(3)]
    assert values == pytest.approx(
        [0.730666524540624, 0.5928898580149862, 0.20213287431010984],
        rel=0,
        abs=1e-15,
    )


def test_rng_mode_switches_between_portable_and_legacy() -> None:
    manager_portable = SeedManager(seed=99)
    manager_legacy = SeedManager(seed=99, rng_mode="legacy")

    assert isinstance(manager_portable.base_random, PortableRandom)
    assert type(manager_legacy.base_random) is random.Random


def test_substreams_are_repeatable_and_distinct() -> None:
    manager_a = SeedManager(seed=1010)
    manager_b = SeedManager(seed=1010)

    value_key0_a = manager_a.random_for("User", "email", 0).random()
    value_key0_b = manager_b.random_for("User", "email", 0).random()
    value_key1_a = manager_a.random_for("User", "email", 1).random()

    assert value_key0_a == value_key0_b
    assert value_key0_a != value_key1_a


def test_faker_locale_and_repeatability() -> None:
    locale = "fr_FR"
    manager_a = SeedManager(seed=2024, locale=locale)
    manager_b = SeedManager(seed=2024, locale=locale)

    locales_a = getattr(manager_a.faker, "locales", [])
    locales_b = getattr(manager_b.faker, "locales", [])

    assert locale in locales_a
    assert locale in locales_b

    name_a = manager_a.faker.name()
    name_b = manager_b.faker.name()

    assert name_a == name_b


def test_child_seed_varies_with_key_parts() -> None:
    manager = SeedManager(seed=555)

    seed_a = manager.derive_child_seed("Model", "field", 0)
    seed_b = manager.derive_child_seed("Model", "field", 1)
    seed_c = manager.derive_child_seed("Model", "other", 0)

    assert seed_a != seed_b
    assert seed_a != seed_c


def test_faker_substreams_distinct() -> None:
    manager = SeedManager(seed=9090, locale="en_US")

    faker_a = manager.faker_for("User", "name", 0)
    faker_b = manager.faker_for("User", "name", 1)

    values_a = [faker_a.pyint() for _ in range(5)]
    values_b = [faker_b.pyint() for _ in range(5)]

    assert values_a != values_b


def test_numpy_rng_repeatable() -> None:
    manager_a = SeedManager(seed=42)
    manager_b = SeedManager(seed=42)

    rng_a = manager_a.numpy_rng
    rng_b = manager_b.numpy_rng

    assert rng_a is not None
    assert rng_b is not None

    array_a = rng_a.random(3)
    array_b = rng_b.random(3)

    assert np.allclose(array_a, array_b)


def test_numpy_substream_repeatable() -> None:
    manager_a = SeedManager(seed="abc")
    manager_b = SeedManager(seed="abc")

    rng_a = manager_a.numpy_for("Model", "field", 2)
    rng_b = manager_b.numpy_for("Model", "field", 2)
    rng_other = manager_a.numpy_for("Model", "field", 3)

    assert rng_a is not None and rng_b is not None

    values_a = rng_a.random(4)
    values_b = rng_b.random(4)

    assert np.allclose(values_a, values_b)

    if rng_other is not None:
        other_values = rng_other.random(4)
        assert not np.allclose(values_a, other_values)


def test_normalized_seed_with_none_and_bytes() -> None:
    manager_none = SeedManager(seed=None)
    manager_bytes = SeedManager(seed=b"bytes-seed")

    assert manager_none.normalized_seed == 0
    assert manager_bytes.normalized_seed == SeedManager(seed=b"bytes-seed").normalized_seed


def test_random_for_returns_cached_instance() -> None:
    manager = SeedManager(seed=77)

    stream_a = manager.random_for("Model", "field")
    stream_b = manager.random_for("Model", "field")

    assert stream_a is stream_b


def test_numpy_for_handles_absent_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = SeedManager(seed=5)
    monkeypatch.setattr("pydantic_fixturegen.core.seed._np", None)

    assert manager.numpy_for("Model", "field") is None
