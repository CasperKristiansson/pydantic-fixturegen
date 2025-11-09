from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.api._runtime import ModelArtifactPlan  # noqa: E402
from pydantic_fixturegen.core.path_template import OutputTemplateContext  # noqa: E402
from pydantic_fixturegen.orm.beanie import (  # noqa: E402
    _clean_payload,
    _expand_sample,
)


class PrimaryModel(BaseModel):
    value: int


class RelatedModel(BaseModel):
    value: int


def _build_plan() -> ModelArtifactPlan:
    return ModelArtifactPlan(
        app_config=SimpleNamespace(seed=None),
        config_snapshot=SimpleNamespace(),
        model_cls=PrimaryModel,
        related_models=(RelatedModel,),
        sample_factory=lambda: {"PrimaryModel": {"value": 1}, "RelatedModel": {"value": 2}},
        template_context=OutputTemplateContext(model="PrimaryModel"),
        base_output=Path("out.json"),
        warnings=(),
        freeze_manager=None,
        model_id="PrimaryModel",
        model_digest=None,
        selected_seed=None,
        reporter=None,
    )


def test_beanie_expand_sample_orders_entries() -> None:
    plan = _build_plan()
    sample = {"PrimaryModel": {"value": 1}, "RelatedModel": {"value": 2}}

    ordered = list(_expand_sample(plan, sample))

    assert ordered[0][0] is RelatedModel
    assert ordered[1][0] is PrimaryModel


def test_beanie_expand_sample_falls_back_to_primary_only() -> None:
    plan = _build_plan()
    expanded = list(_expand_sample(plan, {"value": 9}))
    assert expanded == [(PrimaryModel, {"value": 9})]


def test_beanie_expand_sample_requires_mapping() -> None:
    plan = _build_plan()
    with pytest.raises(RuntimeError):
        list(_expand_sample(plan, 10))  # type: ignore[arg-type]


def test_beanie_clean_payload_discards_cycles() -> None:
    payload = {"value": 3, "__cycles__": [{"path": "PrimaryModel"}]}
    assert _clean_payload(payload) == {"value": 3}
