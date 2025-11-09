from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel
from pydantic_fixturegen.api._runtime import ModelArtifactPlan
from pydantic_fixturegen.core.path_template import OutputTemplateContext
from pydantic_fixturegen.testing.seeders import SQLModelSeedRunner


class _SampleModel(BaseModel):
    value: int


def _build_plan() -> ModelArtifactPlan:
    return ModelArtifactPlan(
        app_config=SimpleNamespace(seed=None),
        config_snapshot=SimpleNamespace(),
        model_cls=_SampleModel,
        related_models=(),
        sample_factory=lambda: {"value": 1},
        template_context=OutputTemplateContext(model="Sample"),
        base_output=Path("sample.json"),
        warnings=(),
        freeze_manager=None,
        model_id="Sample",
        model_digest=None,
        selected_seed=None,
        reporter=None,
    )


def test_sqlmodel_seed_runner_invokes_sqlalchemy_seeder(monkeypatch):
    captured: dict[str, object] = {}

    class DummySeeder:
        def __init__(self, plan: ModelArtifactPlan, session_factory):
            captured["plan"] = plan
            captured["session_factory"] = session_factory

        def seed(
            self,
            *,
            count: int,
            batch_size: int,
            rollback: bool,
            truncate: bool,
            dry_run: bool,
        ) -> None:
            captured["seed_args"] = {
                "count": count,
                "batch_size": batch_size,
                "rollback": rollback,
                "truncate": truncate,
                "dry_run": dry_run,
            }

    monkeypatch.setattr("pydantic_fixturegen.orm.sqlalchemy.SQLAlchemySeeder", DummySeeder)

    runner = SQLModelSeedRunner(plan=_build_plan(), session_factory=lambda: "session")
    runner.seed(count=3, batch_size=20, rollback=False)

    assert isinstance(captured["plan"], ModelArtifactPlan)
    assert callable(captured["session_factory"])
    assert captured["seed_args"] == {
        "count": 3,
        "batch_size": 20,
        "rollback": False,
        "truncate": False,
        "dry_run": False,
    }
