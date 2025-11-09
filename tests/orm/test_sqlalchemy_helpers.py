from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.api._runtime import ModelArtifactPlan
from pydantic_fixturegen.core.path_template import OutputTemplateContext
from pydantic_fixturegen.orm.sqlalchemy import _clean_payload, _expand_sample


class Primary(BaseModel):
    id: int


class Related(BaseModel):
    id: int


def _build_plan() -> ModelArtifactPlan:
    return ModelArtifactPlan(
        app_config=SimpleNamespace(seed=None),
        config_snapshot=SimpleNamespace(),
        model_cls=Primary,
        related_models=(Related,),
        sample_factory=lambda: {"Primary": {"id": 1}, "Related": {"id": 2}},
        template_context=OutputTemplateContext(model="Primary"),
        base_output=Path("out.json"),
        warnings=(),
        freeze_manager=None,
        model_id="Primary",
        model_digest=None,
        selected_seed=None,
        reporter=None,
    )


def test_expand_sample_orders_related_models() -> None:
    plan = _build_plan()
    sample = {"Primary": {"id": 1}, "Related": {"id": 2}}

    ordered = list(_expand_sample(plan, sample))

    assert ordered[0][0] is Related
    assert ordered[0][1] == {"id": 2}
    assert ordered[1][0] is Primary
    assert ordered[1][1] == {"id": 1}


def test_expand_sample_handles_primary_only_payload() -> None:
    plan = _build_plan()
    sample = {"id": 9}

    expanded = list(_expand_sample(plan, sample))
    assert expanded == [(Primary, {"id": 9})]


def test_expand_sample_rejects_non_mappings() -> None:
    plan = _build_plan()
    with pytest.raises(RuntimeError):
        list(_expand_sample(plan, "invalid"))  # type: ignore[arg-type]


def test_clean_payload_drops_cycle_metadata() -> None:
    payload = {"value": 1, "__cycles__": [{"path": "Primary"}]}
    assert _clean_payload(payload) == {"value": 1}
