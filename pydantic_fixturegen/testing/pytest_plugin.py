"""pytest plugin exposing snapshot helpers."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Final, cast

import pytest

from .snapshot import SnapshotResult, SnapshotRunner, SnapshotUpdateMode

UPDATE_OPTION_NAME: Final = "pfg_update_snapshots"
SNAPSHOT_MARKER_NAME: Final = "pfg_snapshot_config"
_RUNNER_OVERRIDE_FIELDS: Final = {"timeout", "memory_limit_mb", "ast_mode", "hybrid_mode"}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pfg")
    group.addoption(
        f"--{UPDATE_OPTION_NAME.replace('_', '-')}",
        action="store",
        dest=UPDATE_OPTION_NAME,
        choices=[mode.value for mode in SnapshotUpdateMode],
        help="Control whether pfg snapshot assertions update files or fail on drift.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        (
            f"{SNAPSHOT_MARKER_NAME}(update='fail', timeout=5.0, memory_limit_mb=256, "
            "ast_mode=False, hybrid_mode=False):\n"
            "    Override the pfg_snapshot fixture for a single test."
        ),
    )


@pytest.fixture
def pfg_snapshot(
    pytestconfig: pytest.Config,
    request: pytest.FixtureRequest,
) -> SnapshotRunner:
    marker_overrides = _get_marker_overrides(request)
    option_value = pytestconfig.getoption(UPDATE_OPTION_NAME, default=None)
    env_mode = os.getenv("PFG_SNAPSHOT_UPDATE")
    update_override = marker_overrides.pop("update", None)
    mode = SnapshotUpdateMode.coerce(update_override or option_value or env_mode)
    runner = SnapshotRunner(update_mode=mode)

    for field, value in marker_overrides.items():
        setattr(runner, field, value)

    force_regen = _safe_getoption(pytestconfig, "force_regen")
    regen_all = _safe_getoption(pytestconfig, "regen_all")
    proxy = _SnapshotFixtureProxy(
        runner,
        force_regen=force_regen,
        regen_all=regen_all,
    )
    return cast(SnapshotRunner, proxy)


def _get_marker_overrides(request: pytest.FixtureRequest) -> dict[str, Any]:
    marker = request.node.get_closest_marker(SNAPSHOT_MARKER_NAME)
    if marker is None:
        return {}

    overrides: dict[str, Any] = dict(marker.kwargs)
    if "update" not in overrides and marker.args:
        overrides["update"] = marker.args[0]

    unknown = set(overrides).difference(_RUNNER_OVERRIDE_FIELDS | {"update"})
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise pytest.UsageError(f"Unknown {SNAPSHOT_MARKER_NAME} option(s): {joined}")

    return overrides


def _safe_getoption(config: pytest.Config, name: str) -> bool:
    try:
        return bool(config.getoption(name))
    except (ValueError, AttributeError):
        return False


class _SnapshotFixtureProxy:
    """Proxy that injects pytest-regressions semantics into SnapshotRunner."""

    def __init__(
        self,
        runner: SnapshotRunner,
        *,
        force_regen: bool,
        regen_all: bool,
        failer: Callable[[str], None] | None = None,
    ) -> None:
        self._runner = runner
        self._force_regen = force_regen
        self._regen_all = regen_all
        self._fail = failer or pytest.fail

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)

    def assert_artifacts(self, *args: Any, **kwargs: Any) -> SnapshotResult:
        update_value = kwargs.get("update")
        if update_value is None and (self._force_regen or self._regen_all):
            kwargs["update"] = SnapshotUpdateMode.UPDATE

        result = self._runner.assert_artifacts(*args, **kwargs)

        if self._force_regen and result.updated:
            self._fail(
                "Snapshots regenerated via --force-regen; rerun without --force-regen after "
                "committing the updated artifacts."
            )
        return result
