"""pytest plugin exposing snapshot helpers."""

from __future__ import annotations

import os

import pytest

from .snapshot import SnapshotRunner, SnapshotUpdateMode

UPDATE_OPTION_NAME = "pfg_update_snapshots"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pfg")
    group.addoption(
        f"--{UPDATE_OPTION_NAME.replace('_', '-')}",
        action="store",
        dest=UPDATE_OPTION_NAME,
        choices=[mode.value for mode in SnapshotUpdateMode],
        help="Control whether pfg snapshot assertions update files or fail on drift.",
    )


@pytest.fixture
def pfg_snapshot(pytestconfig: pytest.Config) -> SnapshotRunner:
    option_value = pytestconfig.getoption(UPDATE_OPTION_NAME, default=None)
    env_mode = os.getenv("PFG_SNAPSHOT_UPDATE")
    mode = SnapshotUpdateMode.coerce(option_value or env_mode)
    runner = SnapshotRunner(update_mode=mode)
    return runner
