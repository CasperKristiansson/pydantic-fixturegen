from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_fixturegen.core.providers import strings as strings_mod
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


class DummyFaker:
    def __init__(self, responses: tuple[str, ...] | None = None) -> None:
        self.responses = list(responses or ())
        self.calls: list[tuple[int, int]] = []

    def pystr(self, *, min_chars: int, max_chars: int) -> str:
        self.calls.append((min_chars, max_chars))
        if self.responses:
            return self.responses.pop(0)
        return "x" * max_chars


def _summary(
    *,
    type_id: str = "string",
    min_length: int | None = None,
    max_length: int | None = None,
    pattern: str | None = None,
) -> FieldSummary:
    constraints = FieldConstraints(min_length=min_length, max_length=max_length, pattern=pattern)
    return FieldSummary(type=type_id, constraints=constraints)


def test_generate_string_respects_length_bounds() -> None:
    faker = DummyFaker()
    summary = _summary(min_length=4, max_length=6)

    result = strings_mod.generate_string(summary, faker=faker)

    assert 4 <= len(result) <= 6
    assert faker.calls[-1] == (4, 6)


def test_generate_string_pattern_uses_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _summary(pattern="^abc.*$")
    faker = DummyFaker(responses=("suffix",))
    original_rstr = getattr(strings_mod, "rstr", None)
    monkeypatch.setattr(strings_mod, "rstr", None, raising=False)

    try:
        result = strings_mod.generate_string(summary, faker=faker)
    finally:
        monkeypatch.setattr(strings_mod, "rstr", original_rstr, raising=False)

    assert result.startswith("abc")
    # Fallback should pad using faker output
    assert result.endswith("suffix")


def test_secret_bytes_length_derived_from_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[int] = []
    def fake_urandom(size: int) -> bytes:
        recorded.append(size)
        return b"x" * size

    monkeypatch.setattr(strings_mod.os, "urandom", fake_urandom)

    summary = _summary(type_id="secret-bytes", min_length=8, max_length=4)

    payload = strings_mod.generate_string(summary)

    assert payload == b"x" * 4
    assert recorded == [4]


def test_ensure_str_raises_for_non_string() -> None:
    with pytest.raises(TypeError):
        strings_mod._ensure_str(123)  # type: ignore[arg-type]


def test_apply_length_pads_and_truncates() -> None:
    summary = _summary(min_length=5, max_length=6)
    faker = DummyFaker(responses=("yy",))

    padded = strings_mod._apply_length("abc", summary, faker=faker)
    assert len(padded) >= 5

    truncated = strings_mod._apply_length("abcdefghi", summary, faker=faker)
    assert len(truncated) == 6


def test_generate_string_unknown_type() -> None:
    with pytest.raises(ValueError):
        strings_mod.generate_string(replace(_summary(), type="uuid"))
