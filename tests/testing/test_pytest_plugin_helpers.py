from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.cli.diff import DiffReport
from pydantic_fixturegen.testing import pytest_plugin
from pydantic_fixturegen.testing.snapshot import SnapshotResult, SnapshotUpdateMode


class DummyMarker:
    def __init__(
        self,
        args: tuple[object, ...] = (),
        kwargs: dict[str, object] | None = None,
    ) -> None:
        self.args = args
        self.kwargs = kwargs or {}


class DummyRequest:
    def __init__(self, marker: DummyMarker | None) -> None:
        self.node = SimpleNamespace(get_closest_marker=lambda name: marker)


def test_get_marker_overrides_uses_positional_update() -> None:
    marker = DummyMarker(args=("update-mode",))
    request = DummyRequest(marker)

    overrides = pytest_plugin._get_marker_overrides(request)
    assert overrides["update"] == "update-mode"


def test_get_marker_overrides_rejects_unknown_options() -> None:
    marker = DummyMarker(kwargs={"unsupported": True})
    request = DummyRequest(marker)

    with pytest.raises(pytest.UsageError):
        pytest_plugin._get_marker_overrides(request)


class _DummyRunner:
    def __init__(self, result: SnapshotResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def assert_artifacts(self, *args, **kwargs):
        self.calls.append(kwargs)
        return self._result


def _make_result(updated: bool) -> SnapshotResult:
    report = DiffReport(
        kind="json",
        target=Path("snap.json"),
        checked_paths=[],
        messages=[],
        diff_outputs=[],
        summary="",
    )
    return SnapshotResult(reports=(report,), updated=updated, mode=SnapshotUpdateMode.UPDATE)


class ProxyFailure(Exception):
    pass


def test_snapshot_proxy_force_regen_fails_when_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    failure_messages: list[str] = []

    def fake_fail(message: str) -> None:
        failure_messages.append(message)
        raise ProxyFailure(message)

    proxy = pytest_plugin._SnapshotFixtureProxy(
        _DummyRunner(_make_result(updated=True)),
        force_regen=True,
        regen_all=False,
        failer=fake_fail,
    )

    with pytest.raises(ProxyFailure):
        proxy.assert_artifacts("models:User", json=None)
    assert failure_messages, "force_regen should raise when snapshots were updated"


def test_snapshot_proxy_force_regen_skips_when_clean() -> None:
    proxy = pytest_plugin._SnapshotFixtureProxy(
        _DummyRunner(_make_result(updated=False)),
        force_regen=True,
        regen_all=False,
    )
    proxy.assert_artifacts("models:User", json=None)


def test_snapshot_proxy_overrides_update_for_regen_all() -> None:
    runner = _DummyRunner(_make_result(updated=False))
    proxy = pytest_plugin._SnapshotFixtureProxy(
        runner,
        force_regen=False,
        regen_all=True,
    )
    proxy.assert_artifacts("models:User", json=None)
    assert runner.calls[0]["update"] is SnapshotUpdateMode.UPDATE


def test_snapshot_proxy_respects_explicit_update_request() -> None:
    runner = _DummyRunner(_make_result(updated=False))
    proxy = pytest_plugin._SnapshotFixtureProxy(
        runner,
        force_regen=False,
        regen_all=True,
    )
    proxy.assert_artifacts(
        "models:User",
        json=None,
        update=SnapshotUpdateMode.FAIL,
    )
    assert runner.calls[0]["update"] is SnapshotUpdateMode.FAIL
