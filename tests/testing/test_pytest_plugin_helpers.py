from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_fixturegen.testing import pytest_plugin


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
