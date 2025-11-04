from __future__ import annotations

import datetime
from pathlib import Path

import pytest
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


def test_output_template_blocks_parent_escape(tmp_path: Path) -> None:
    template = OutputTemplate(tmp_path / "../{model}/data.json")
    context = OutputTemplateContext(model="User")

    with pytest.raises(OutputTemplateError) as exc_info:
        template.render(context=context)

    assert "cannot traverse" in str(exc_info.value)
