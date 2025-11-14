"""String-related providers for pydantic-fixturegen."""

from __future__ import annotations

import os
import random
from types import ModuleType
from typing import Any

try:  # Optional dependency for regex generation
    import rstr as _rstr
except ImportError:  # pragma: no cover - optional extra not installed
    rstr: ModuleType | None = None
else:
    rstr = _rstr

from faker import Faker

from pydantic_fixturegen.core.providers import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary

DEFAULT_MIN_CHARS = 1
DEFAULT_MAX_CHARS = 16


def generate_string(
    summary: FieldSummary,
    *,
    faker: Faker | None = None,
    random_generator: random.Random | None = None,
) -> str | bytes:
    """Generate a string that satisfies the provided constraints."""

    if summary.type not in {"string", "secret-str", "secret-bytes"}:
        raise ValueError(f"Unsupported string type: {summary.type}")

    faker = faker or Faker()
    rng = random_generator or random.Random()

    if summary.type == "secret-str":
        return _random_string(rng, summary, faker=faker)
    if summary.type == "secret-bytes":
        length = _determine_length(summary)
        return os.urandom(length)

    if summary.constraints.pattern:
        return _regex_string(summary, faker=faker)
    return _random_string(rng, summary, faker=faker)


def register_string_providers(registry: ProviderRegistry) -> None:
    registry.register(
        "string",
        generate_string,
        name="string.default",
        metadata={"description": "Faker-backed string provider"},
    )
    registry.register(
        "slug",
        generate_slug,
        name="string.slug",
        metadata={"description": "Deterministic slug generator"},
    )


def _regex_string(summary: FieldSummary, *, faker: Faker) -> str:
    pattern = summary.constraints.pattern or ".*"
    candidate: str
    if rstr is not None:
        if hasattr(rstr, "Xeger"):
            candidate = rstr.Xeger(_random=faker.random).xeger(pattern)
        elif hasattr(rstr, "xeger"):
            candidate = rstr.xeger(pattern)
        else:
            candidate = None
    else:
        candidate = None
    if candidate is None:
        try:
            candidate = faker.regexify(pattern)
        except Exception:
            candidate = _fallback_regex(  # pragma: no cover - fallback path
                pattern,
                faker,
            )
    return _apply_length(candidate, summary, faker=faker)


def _fallback_regex(pattern: str, faker: Faker) -> str:
    stripped = pattern.strip("^$")
    if not stripped:
        return _ensure_str(faker.pystr(min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS))
    # crude fallback: ensure prefix matches stripped text ignoring regex tokens
    prefix = "".join(ch for ch in stripped if ch.isalnum())
    remainder = _ensure_str(faker.pystr(min_chars=0, max_chars=max(DEFAULT_MIN_CHARS, len(prefix))))
    return prefix + remainder


def _random_string(rng: random.Random, summary: FieldSummary, *, faker: Faker) -> str:
    min_chars, max_chars = _length_bounds(summary)
    # Faker's pystr respects min/max characters
    return _ensure_str(faker.pystr(min_chars=min_chars, max_chars=max_chars))


def generate_slug(
    summary: FieldSummary,
    *,
    faker: Faker | None = None,
) -> str:
    """Generate URL-friendly slugs respecting length constraints."""

    faker = faker or Faker()
    slug = _ensure_str(faker.slug()).replace("_", "-")
    slug = slug.strip("- ") or "data"
    min_chars, max_chars = _length_bounds(summary)
    while len(slug) < min_chars:
        extra = _ensure_str(faker.slug()).replace("_", "-")
        slug = f"{slug}-{extra}" if slug else extra
    if len(slug) > max_chars:
        slug = slug[:max_chars].rstrip("-")
    return slug or "data"


def _apply_length(value: str, summary: FieldSummary, *, faker: Faker) -> str:
    min_chars, max_chars = _length_bounds(summary)
    if len(value) < min_chars:
        padding = _ensure_str(
            faker.pystr(min_chars=min_chars - len(value), max_chars=min_chars - len(value))
        )
        value = value + padding
    if len(value) > max_chars:
        value = value[:max_chars]
    return value


def _length_bounds(summary: FieldSummary) -> tuple[int, int]:
    min_chars = summary.constraints.min_length or DEFAULT_MIN_CHARS
    max_chars = summary.constraints.max_length or max(min_chars, DEFAULT_MAX_CHARS)
    if min_chars > max_chars:
        min_chars = max_chars
    return min_chars, max_chars


def _determine_length(summary: FieldSummary) -> int:
    min_chars, max_chars = _length_bounds(summary)
    return max(min_chars, min(max_chars, DEFAULT_MAX_CHARS))


def _ensure_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("Faker returned a non-string value")


__all__ = ["generate_string", "generate_slug", "register_string_providers"]
