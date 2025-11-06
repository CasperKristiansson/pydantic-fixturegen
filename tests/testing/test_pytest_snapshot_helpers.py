from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic_fixturegen.testing.pytest_plugin import (
    UPDATE_OPTION_NAME,
    pfg_snapshot,
    pytest_addoption,
)
from pydantic_fixturegen.testing.snapshot import SnapshotRunner, SnapshotUpdateMode


@dataclass
class _DummyConfig:
    option_value: str | None

    def getoption(self, name: str, default=None):
        assert name == UPDATE_OPTION_NAME
        return self.option_value if self.option_value is not None else default


def test_pytest_addoption_registers_update_flag() -> None:
    recorded: dict[str, dict[str, object]] = {}

    class DummyGroup:
        def addoption(self, *args, **kwargs):
            recorded["args"] = {"args": args, "kwargs": kwargs}

    class DummyParser:
        def getgroup(self, name: str):
            assert name == "pfg"
            return DummyGroup()

    parser = DummyParser()
    pytest_addoption(parser)  # type: ignore[arg-type]

    assert recorded
    args = recorded["args"]["args"]
    kwargs = recorded["args"]["kwargs"]
    assert args == (f"--{UPDATE_OPTION_NAME.replace('_', '-')}",)
    assert kwargs["choices"] == [mode.value for mode in SnapshotUpdateMode]


def test_pfg_snapshot_prefers_cli_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PFG_SNAPSHOT_UPDATE", raising=False)
    runner = pfg_snapshot.__wrapped__(pytestconfig=_DummyConfig(option_value="update"))

    assert isinstance(runner, SnapshotRunner)
    assert runner.update_mode is SnapshotUpdateMode.UPDATE


def test_pfg_snapshot_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFG_SNAPSHOT_UPDATE", "update")
    runner = pfg_snapshot.__wrapped__(pytestconfig=_DummyConfig(option_value=None))

    assert runner.update_mode is SnapshotUpdateMode.UPDATE


def test_snapshot_update_mode_coerce_handles_variants() -> None:
    assert SnapshotUpdateMode.coerce(" UPDATE ") is SnapshotUpdateMode.UPDATE
    assert SnapshotUpdateMode.coerce(None) is SnapshotUpdateMode.FAIL
    with pytest.raises(ValueError):
        SnapshotUpdateMode.coerce("invalid")


def test_snapshot_update_mode_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFG_SNAPSHOT_UPDATE", "fail")
    assert SnapshotUpdateMode.from_env() is SnapshotUpdateMode.FAIL
    monkeypatch.setenv("PFG_SNAPSHOT_UPDATE", "update")
    assert SnapshotUpdateMode.from_env() is SnapshotUpdateMode.UPDATE
    monkeypatch.delenv("PFG_SNAPSHOT_UPDATE", raising=False)
    assert SnapshotUpdateMode.from_env() is SnapshotUpdateMode.FAIL
