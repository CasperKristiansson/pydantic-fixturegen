from __future__ import annotations

from pydantic_fixturegen.core.providers import strings
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def test_generate_string_regex_fallback(monkeypatch) -> None:
    monkeypatch.setattr(strings, "rstr", None)
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(pattern="^abc$", min_length=3, max_length=5),
    )
    value = strings.generate_string(summary)
    assert value.startswith("abc")
