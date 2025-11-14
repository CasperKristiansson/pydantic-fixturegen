from __future__ import annotations

from pydantic_fixturegen import api
from pydantic_fixturegen.api.models import ConfigSnapshot, PersistenceRunResult


def test_api_persist_normalizes_sequences(monkeypatch):
    captured: dict[str, object] = {}
    snapshot = ConfigSnapshot(
        seed=None,
        include=(),
        exclude=(),
        time_anchor=None,
    )

    def fake_persist_samples(**kwargs):
        captured.update(kwargs)
        return PersistenceRunResult(
            handler=kwargs["handler"],
            batches=0,
            records=0,
            retries=0,
            duration=0.0,
            model=object,
            config=snapshot,
            warnings=(),
        )

    monkeypatch.setattr(api, "persist_samples", fake_persist_samples)

    result = api.persist(
        target="models.py",
        handler="memory",
        include=["models.User"],
        exclude=("models.Admin",),
        seed=123,
    )

    assert isinstance(result, PersistenceRunResult)
    assert captured["include"] == ("models.User",)
    assert captured["seed"] == 123
