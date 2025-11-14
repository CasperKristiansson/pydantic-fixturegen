from __future__ import annotations

import pytest
from pydantic_fixturegen.core.providers import temporal as temporal_mod
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def test_generate_temporal_rejects_unknown_type() -> None:
    summary = FieldSummary(type="timestamp", constraints=FieldConstraints())
    with pytest.raises(ValueError):
        temporal_mod.generate_temporal(summary)
