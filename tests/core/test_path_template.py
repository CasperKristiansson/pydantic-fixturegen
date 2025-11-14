from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from pydantic_fixturegen.core import path_template as path_mod
from pydantic_fixturegen.core.path_template import (
    OutputTemplate,
    OutputTemplateContext,
    OutputTemplateError,
)


def test_output_template_render_with_all_fields(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "{model}" / "sample-{case_index}-{timestamp}.json")
    context = OutputTemplateContext(
        model="UserProfile",
        timestamp=datetime.datetime(2024, 7, 21, 12, 30, tzinfo=datetime.timezone.utc),
    )

    rendered = template.render(context=context, case_index=3)

    assert rendered.parent.name == "UserProfile"
    assert rendered.name.startswith("sample-3-20240721")
    assert rendered.suffix == ".json"


def test_output_template_requires_case_index() -> None:
    template = OutputTemplate("artifacts/{case_index}.json")
    context = OutputTemplateContext(model="Artifact")

    with pytest.raises(OutputTemplateError):
        template.render(context=context)


def test_output_template_unknown_variable() -> None:
    with pytest.raises(OutputTemplateError) as exc_info:
        OutputTemplate("{unknown}/file.json")

    assert "unsupported" in str(exc_info.value).lower()


def test_output_template_watch_parent_and_preview(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "artifacts" / "{model}" / "data.json")
    watch_parent = template.watch_parent()
    assert watch_parent == tmp_path / "artifacts"
    preview = template.preview_path()
    assert preview.parent.name == "preview"


def test_output_template_allows_parent_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target_dir = tmp_path.parent / "outside"
    template = OutputTemplate("../outside/{model}/data.json")
    context = OutputTemplateContext(model="User")

    rendered = template.render(context=context)

    assert rendered == target_dir / "User" / "data.json"


def test_strict_formatter_missing_and_positional_fields() -> None:
    formatter = path_mod._StrictFormatter()
    with pytest.raises(OutputTemplateError):
        formatter.format("{model}")

    with pytest.raises(OutputTemplateError):
        formatter.format("{}", "value")


def test_template_case_index_and_timestamp_handling() -> None:
    timestamp = path_mod._TemplateTimestamp(
        datetime.datetime(2024, 5, 4, 3, 2, 1, tzinfo=datetime.timezone.utc)
    )
    formatted = format(timestamp, "%Y/%m/%d")
    assert "/" not in formatted
    assert str(timestamp).startswith("20240504")

    with pytest.raises(OutputTemplateError):
        path_mod._TemplateCaseIndex(0)

    padded = format(path_mod._TemplateCaseIndex(3), "03")
    assert padded == "003"
    assert str(path_mod._TemplateCaseIndex(2)) == "2"


def test_template_string_and_sanitize_helpers() -> None:
    fallback = path_mod._TemplateString("!!!")
    assert fallback == "artifact"

    sanitized = path_mod.sanitize_path_segment(" value /with spaces ")
    assert sanitized == "value_with_spaces"


def test_watch_parent_without_stable_segments() -> None:
    template = OutputTemplate("{model}-{case_index}.json")
    assert template.watch_parent() == Path(".")


def test_watch_parent_stops_before_placeholder() -> None:
    template = OutputTemplate("static/{model}/data.json")
    assert template.watch_parent() == Path("static")


def test_render_rejects_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    template = OutputTemplate("{model}")
    dummy_formatter = type(
        "DummyFormatter",
        (),
        {"format": lambda self, raw, **kwargs: "   "},  # noqa: ARG001
    )()
    template._formatter = dummy_formatter  # type: ignore[attr-defined]

    with pytest.raises(OutputTemplateError):
        template.render(context=OutputTemplateContext(model="ignored"), case_index=None)
