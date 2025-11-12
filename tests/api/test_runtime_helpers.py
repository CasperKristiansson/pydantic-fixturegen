from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.api import _runtime as runtime_mod
from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.core.config import AppConfig
from pydantic_fixturegen.core.cycle_report import CycleEvent, attach_cycle_events
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError
from pydantic_fixturegen.core.generate import InstanceGenerator
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.polyfactory_support.discovery import PolyfactoryBinding


def _app_config(**overrides: object) -> AppConfig:
    default_config = AppConfig()
    return dataclasses.replace(default_config, **overrides)


def test_snapshot_config_and_details_roundtrip() -> None:
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    config = _app_config(seed=42, include=("foo",), exclude=("bar",), now=now)
    snapshot = runtime_mod._snapshot_config(config)

    assert snapshot.seed == 42
    details = runtime_mod._config_details(snapshot)
    assert details["include"] == ["foo"]
    assert details["time_anchor"] == now.isoformat()


def test_split_and_resolve_patterns() -> None:
    raw = " modelA , modelB "
    assert runtime_mod._split_patterns(raw) == ["modelA", "modelB"]
    assert runtime_mod._split_patterns(None) == []
    assert runtime_mod._resolve_patterns(["one, two", " three "]) == ["one", "two", "three"]
    assert runtime_mod._resolve_patterns(None) is None


def test_collect_warnings_trims_empty() -> None:
    warnings = runtime_mod._collect_warnings(["  warn  ", "", "note"])
    assert warnings == ("warn", "note")


def test_build_error_details_and_attach() -> None:
    snapshot = ConfigSnapshot(
        seed=None,
        include=("a",),
        exclude=(),
        time_anchor=None,
    )
    details = runtime_mod._build_error_details(
        config_snapshot=snapshot,
        warnings=("w1",),
        base_output=Path("out"),
        constraint_summary={"fields": 1},
    )
    exc = EmitError("failed", details={})
    runtime_mod._attach_error_details(exc, details)

    assert exc.details["warnings"] == ["w1"]
    assert exc.details["constraint_summary"] == {"fields": 1}


def test_summarize_constraint_report_handles_non_dict() -> None:
    class Reporter:
        def summary(self):
            return {"ok": True}

    class NoneReporter:
        def summary(self):
            return ["unexpected"]

    assert runtime_mod._summarize_constraint_report(Reporter()) == {"ok": True}
    assert runtime_mod._summarize_constraint_report(NoneReporter()) is None
    assert runtime_mod._summarize_constraint_report(None) is None


def test_build_instance_generator_seed_handling() -> None:
    config = _app_config(seed=7, p_none=0.5)
    generator = runtime_mod._build_instance_generator(config)

    assert isinstance(generator, InstanceGenerator)
    assert generator.config.seed is not None
    assert generator.config.optional_p_none == 0.5

    override = runtime_mod._build_instance_generator(config, seed_override=123)
    assert override.config.seed == 123


def test_dataset_columns_handles_existing_cycles() -> None:
    class FakeModel:
        model_fields = {"__cycles__": object()}

    assert runtime_mod._dataset_columns(FakeModel) == tuple(FakeModel.model_fields.keys())


def test_dataset_columns_appends_cycles() -> None:
    class Example(BaseModel):
        value: int

    assert runtime_mod._dataset_columns(Example)[-1] == "__cycles__"


def test_collect_polyfactory_bindings_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _app_config(polyfactory=dataclasses.replace(AppConfig().polyfactory, enabled=False))
    bindings = runtime_mod._collect_polyfactory_bindings(
        app_config=config,
        discovery=None,
        model_class_lookup=None,
        logger=get_logger(),
    )
    assert bindings == ()


def test_collect_polyfactory_bindings_missing_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _app_config()
    bindings = runtime_mod._collect_polyfactory_bindings(
        app_config=config,
        discovery=None,
        model_class_lookup=None,
        logger=get_logger(),
    )
    assert bindings == ()


def test_maybe_enable_polyfactory_delegation_respects_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _app_config(
        polyfactory=dataclasses.replace(AppConfig().polyfactory, prefer_delegation=False)
    )
    flag = {"called": False}

    def fake_attach(generator, bindings, logger):  # pragma: no cover - defensive
        flag["called"] = True

    monkeypatch.setattr(
        "pydantic_fixturegen.polyfactory_support.attach_polyfactory_bindings",
        fake_attach,
    )

    generator = runtime_mod._build_instance_generator(config)
    runtime_mod._maybe_enable_polyfactory_delegation(
        generator=generator,
        app_config=config,
        bindings=(SimpleNamespace(),),
        logger=get_logger(),
    )
    assert flag["called"] is False


def test_rebase_polyfactory_bindings_matches_models() -> None:
    Source = type("Widget", (BaseModel,), {})
    Source.__module__ = "external.pkg"
    Target = type("Widget", (BaseModel,), {})

    factory = SimpleNamespace(__model__=Source)
    binding = PolyfactoryBinding(model=Source, factory=factory, source="auto")
    rebased = runtime_mod._rebase_polyfactory_bindings(
        (binding,),
        {Source.__qualname__: Target},
    )

    assert rebased[0].model is Target


def test_build_model_artifact_plan_validates_target(tmp_path: Path) -> None:
    template = OutputTemplate(str(tmp_path / "out.json"))
    logger = get_logger()

    with pytest.raises(DiscoveryError):
        runtime_mod._build_model_artifact_plan(
            target_path=tmp_path / "missing.py",
            output_template=template,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
            respect_validators=None,
            validator_max_retries=None,
            relations=None,
            with_related=None,
            logger=logger,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            field_overrides=None,
            field_hints=None,
            payload_mode="python",
        )

    directory = tmp_path / "pkg"
    directory.mkdir()

    with pytest.raises(DiscoveryError):
        runtime_mod._build_model_artifact_plan(
            target_path=directory,
            output_template=template,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
            respect_validators=None,
            validator_max_retries=None,
            relations=None,
            with_related=None,
            logger=logger,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            field_overrides=None,
            field_hints=None,
            payload_mode="python",
        )


def test_dataset_columns_appends_cycle_field() -> None:
    class Example(BaseModel):
        id: int

    class WithCycles(BaseModel):
        __cycles__: list[str]

    assert runtime_mod._dataset_columns(Example) == ("id", "__cycles__")
    assert runtime_mod._dataset_columns(WithCycles) == ("__cycles__",)


def test_build_relation_model_map_registers_aliases() -> None:
    class Alpha(BaseModel):
        id: int

    class Beta(BaseModel):
        id: int

    mapping = runtime_mod._build_relation_model_map([Alpha, Beta])
    assert mapping["Alpha"] is Alpha
    assert mapping[Alpha.__qualname__] is Alpha
    assert any(cls is Beta for cls in mapping.values())


def test_instance_payload_includes_cycle_metadata() -> None:
    class Record(BaseModel):
        value: int

    instance = Record(value=1)
    attach_cycle_events(
        instance,
        [
            CycleEvent(
                path="$.value",
                policy="reuse",
                reason="cycle",
                ref_path="$.value",
                fallback="stub",
            )
        ],
    )

    payload = runtime_mod._instance_payload(instance, model=Record)
    assert payload["__cycles__"][0]["path"] == "$.value"
