"""Deterministic seed plumbing for random, Faker, and optional NumPy streams."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Literal, TypeVar, cast

from faker import Faker

try:  # pragma: no cover - optional dependency
    _np = cast(Any, import_module("numpy"))
except ModuleNotFoundError:  # pragma: no cover - numpy optional
    _np = None

DEFAULT_LOCALE = "en_US"
_SEPARATOR = b"\x1f"  # unit separator for hash derivation


def _normalize_seed(seed: Any | None) -> int:
    """Normalize seed inputs to an integer suitable for RNGs."""
    if isinstance(seed, int):
        return seed

    if seed is None:
        return 0

    payload = seed if isinstance(seed, bytes) else str(seed).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:16], "big", signed=False)


def _create_faker(locale: str, seed: int) -> Faker:
    faker = Faker(locale)
    faker.seed_instance(seed)
    return faker


def _create_numpy_rng(seed: int) -> Any | None:
    if _np is None:
        return None

    bit_gen = _np.random.PCG64(seed)  # pragma: no cover
    return _np.random.Generator(bit_gen)  # pragma: no cover


def _seed_bytes(seed: int) -> bytes:
    return str(seed).encode("utf-8")


class PortableRandom(random.Random):
    """Random generator backed by SplitMix64 for cross-platform determinism."""

    _MASK = (1 << 64) - 1

    def __init__(self, seed: Any | None = None) -> None:
        super().__init__()
        self._state = 0
        self.seed(seed)

    def seed(self, a: Any | None = None, version: int = 2) -> None:  # noqa: ARG002
        value = _normalize_seed(a)
        if value == 0:
            value = 0x9E3779B97F4A7C15
        self._state = value & self._MASK

    def getstate(self) -> tuple[int]:
        return (self._state,)

    def setstate(self, state: tuple[int, ...]) -> None:
        (value,) = state
        self._state = value & self._MASK

    def _next_uint64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & self._MASK
        z = self._state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & self._MASK
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & self._MASK
        z ^= z >> 31
        return z & self._MASK

    def random(self) -> float:
        return (self._next_uint64() >> 11) / float(1 << 53)


SeedKey = tuple[Any, ...]
T = TypeVar("T")
RNGModeLiteral = Literal["portable", "legacy"]


@dataclass
class SeedManager:
    """Manage deterministic random streams derived from a master seed."""

    seed: Any | None = None
    locale: str = DEFAULT_LOCALE
    rng_mode: RNGModeLiteral = "portable"

    _normalized_seed: int = field(init=False, repr=False)
    _seed_bytes: bytes = field(init=False, repr=False)
    _base_random: random.Random = field(init=False, repr=False)
    _faker: Faker = field(init=False, repr=False)
    _numpy_rng: Any | None = field(init=False, repr=False)
    _random_ctor: type[random.Random] = field(init=False, repr=False)
    _random_cache: dict[SeedKey, random.Random] = field(
        default_factory=dict, init=False, repr=False
    )
    _faker_cache: dict[SeedKey, Faker] = field(default_factory=dict, init=False, repr=False)
    _numpy_cache: dict[SeedKey, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._normalized_seed = _normalize_seed(self.seed)
        self._seed_bytes = _seed_bytes(self._normalized_seed)
        self._random_ctor = PortableRandom if self.rng_mode == "portable" else random.Random
        self._base_random = self._random_ctor(self._normalized_seed)
        self._faker = _create_faker(self.locale, self._normalized_seed)
        self._numpy_rng = _create_numpy_rng(self._normalized_seed)

    @property
    def normalized_seed(self) -> int:
        """Return the normalized integer seed."""
        return self._normalized_seed

    @property
    def base_random(self) -> random.Random:
        """Random generator seeded with the master seed."""
        return self._base_random

    @property
    def faker(self) -> Faker:
        """Faker instance seeded with the master seed."""
        return self._faker

    @property
    def numpy_rng(self) -> Any | None:
        """NumPy random generator seeded with the master seed (if NumPy is available)."""
        return self._numpy_rng  # pragma: no cover - optional dependency

    def derive_child_seed(self, *parts: Any) -> int:
        """Derive a deterministic child seed from the master seed and supplied key parts."""
        hasher = hashlib.sha256()
        hasher.update(self._seed_bytes)

        for part in parts:
            hasher.update(_SEPARATOR)
            hasher.update(str(part).encode("utf-8"))

        digest = hasher.digest()
        return int.from_bytes(digest[:16], "big", signed=False)

    def _cache_get_or_create(
        self, cache: dict[SeedKey, T], key: SeedKey, factory: Callable[[SeedKey], T]
    ) -> T:
        if key not in cache:
            cache[key] = factory(key)
        return cache[key]

    def random_for(self, *parts: Any) -> random.Random:
        """Return a deterministic `random.Random` stream for the given key parts."""
        key = tuple(parts)

        def factory(_: SeedKey) -> random.Random:
            return self._random_ctor(self.derive_child_seed(*parts))

        return self._cache_get_or_create(self._random_cache, key, factory)

    def faker_for(self, *parts: Any) -> Faker:
        """Return a Faker instance seeded for the given key parts."""
        key = tuple(parts)

        def factory(_: SeedKey) -> Faker:
            faker = Faker(self.locale)
            faker.seed_instance(self.derive_child_seed(*parts))
            return faker

        return self._cache_get_or_create(self._faker_cache, key, factory)

    def numpy_for(self, *parts: Any) -> Any | None:
        """Return a NumPy generator seeded for the given key (if NumPy is available)."""
        if _np is None:
            return None
        else:  # pragma: no cover
            key = tuple(parts)

            def factory(_: SeedKey) -> Any:
                seed = self.derive_child_seed(*parts)
                bit_gen = _np.random.PCG64(seed)  # pragma: no cover
                return _np.random.Generator(bit_gen)  # pragma: no cover

            return self._cache_get_or_create(self._numpy_cache, key, factory)


__all__ = ["SeedManager", "PortableRandom", "DEFAULT_LOCALE", "RNGModeLiteral"]
