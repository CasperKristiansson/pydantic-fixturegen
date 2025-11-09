from __future__ import annotations

from itertools import cycle

from faker import Faker
from pydantic_fixturegen.core.providers import strings
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pytest import MonkeyPatch


def test_generate_string_regex_fallback(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(strings, "rstr", None)
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(pattern="^abc$", min_length=3, max_length=5),
    )
    value = strings.generate_string(summary)
    assert isinstance(value, str)
    assert value.startswith("abc")


def test_generate_slug_expands_to_min_length(monkeypatch: MonkeyPatch) -> None:
    calls = cycle(["core", "longer-segment"])

    faker = Faker()

    def fake_slug():
        return next(calls)

    monkeypatch.setattr(faker, "slug", fake_slug)
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=25, max_length=40),
        format="slug",
    )

    value = strings.generate_slug(summary, faker=faker)
    assert len(value) >= 25
    assert "longer-segment" in value


def test_generate_slug_trims_max_length(monkeypatch: MonkeyPatch) -> None:
    faker = Faker()
    monkeypatch.setattr(faker, "slug", lambda: "pydantic-fixturegen-provider")
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=3, max_length=10),
        format="slug",
    )

    value = strings.generate_slug(summary, faker=faker)
    assert len(value) <= 10
    assert value == value.strip("-")
