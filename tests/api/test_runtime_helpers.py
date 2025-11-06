from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

from pydantic_fixturegen.api import _runtime as runtime_mod
from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.core.config import AppConfig
from pydantic_fixturegen.core.errors import EmitError
from pydantic_fixturegen.core.generate import InstanceGenerator


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
