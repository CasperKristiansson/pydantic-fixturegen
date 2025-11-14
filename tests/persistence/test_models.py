from __future__ import annotations

import datetime as dt

from pydantic_fixturegen.api.models import ConfigSnapshot
from pydantic_fixturegen.logging import get_logger
from pydantic_fixturegen.persistence import models as persistence_models


def test_json_default_handles_special_types() -> None:
    sample_dt = dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    sample_set = {3, 1}

    assert persistence_models._json_default(sample_dt) == sample_dt.isoformat()
    assert persistence_models._json_default(b"bytes") == "bytes"
    assert persistence_models._json_default(sample_set) == [1, 3]

    class Hexy:
        def hex(self) -> str:
            return "feed"

    method = persistence_models._json_default(Hexy())
    assert callable(method)
    assert method() == "feed"
    assert "object" in persistence_models._json_default(object())


def test_dumps_payload_uses_default_encoder() -> None:
    payload = {"values": {2, 1}}

    rendered = persistence_models.dumps_payload(payload)

    assert '"values": [1, 2]' in rendered


def test_persistence_record_to_json_serializes_payload() -> None:
    record = persistence_models.PersistenceRecord(
        model="Sample",
        payload={"value": 1},
        case_index=1,
    )

    assert record.to_json() == '{"value": 1}'


def test_persistence_stats_helpers_track_counts() -> None:
    stats = persistence_models.PersistenceStats(handler_name="test")

    stats.record_batch(3)
    stats.record_retry()

    assert stats.batches == 1
    assert stats.records == 3
    assert stats.retries == 1


def test_persistence_context_holds_metadata() -> None:
    ctx = persistence_models.PersistenceContext(
        model=dict,
        related_models=(),
        total_records=10,
        batch_size=5,
        handler_name="handler",
        options={},
        run_id="abc",
        warnings=("warn",),
        logger=get_logger(),
        config=ConfigSnapshot(
            seed=None,
            include=(),
            exclude=(),
            time_anchor=None,
        ),
        metadata={"source": "tests"},
    )

    assert ctx.metadata["source"] == "tests"
