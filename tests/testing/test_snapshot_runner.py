from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.testing.snapshot import (
    FixturesSnapshotConfig,
    JsonSnapshotConfig,
    SchemaSnapshotConfig,
    SnapshotAssertionError,
    SnapshotResult,
    SnapshotRunner,
    SnapshotUpdateMode,
    _build_fixtures_options,
    _build_json_options,
    _build_schema_options,
    _format_failure_message,
    _normalize_patterns,
)


class DummyReport:
    def __init__(self, changed: bool, kind: str = "json") -> None:
        self.changed = changed
        self.kind = kind
        self.target = "sample"
        self.messages: list[str] = ["drift detected"]
        self.diff_outputs = [("path", "diff")]
        self.summary = "summary"


def test_snapshot_runner_requires_configuration() -> None:
    runner = SnapshotRunner()
    with pytest.raises(ValueError):
        runner.assert_artifacts("models:User")


def test_snapshot_runner_returns_when_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = SnapshotRunner()

    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot._execute_diff",
        lambda **kwargs: [DummyReport(changed=False)],
    )

    result = runner.assert_artifacts("models:User", json=JsonSnapshotConfig(out=Path("out.json")))
    assert result.updated is False


def test_snapshot_runner_updates_and_rechecks(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = SnapshotRunner(update_mode=SnapshotUpdateMode.UPDATE)
    diff_calls: list[list[DummyReport]] = []

    def fake_diff(**kwargs: Any):
        report = DummyReport(changed=len(diff_calls) == 0)
        diff_calls.append([report])
        return diff_calls[-1]

    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot._execute_diff",
        fake_diff,
    )

    updated: dict[str, bool] = {}

    def fake_update(self, **kwargs: Any) -> None:
        updated["called"] = True

    monkeypatch.setattr(SnapshotRunner, "_update_artifacts", fake_update, raising=False)

    result = runner.assert_artifacts("models:User", json=JsonSnapshotConfig(out=Path("snap.json")))
    assert updated.get("called") is True
    assert result.updated is True


def test_snapshot_runner_raises_when_changes_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = SnapshotRunner(update_mode=SnapshotUpdateMode.UPDATE)

    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot._execute_diff",
        lambda **kwargs: [DummyReport(changed=True)],
    )
    monkeypatch.setattr(
        SnapshotRunner,
        "_update_artifacts",
        lambda *args, **kwargs: None,
        raising=False,
    )

    with pytest.raises(SnapshotAssertionError):
        runner.assert_artifacts("models:User", json=JsonSnapshotConfig(out=Path("snap.json")))


def test_snapshot_helpers_build_defaults() -> None:
    assert _normalize_patterns(None) is None
    assert _normalize_patterns(["  foo  "]) == "foo"

    json_options = _build_json_options(None)
    assert json_options.count == 1

    fixtures_options = _build_fixtures_options(None)
    assert fixtures_options.cases == 1

    schema_options = _build_schema_options(None)
    assert schema_options.out is None
    with pytest.raises(ValueError):
        SnapshotUpdateMode.coerce("invalid-mode")
    assert SnapshotUpdateMode.coerce(SnapshotUpdateMode.UPDATE) is SnapshotUpdateMode.UPDATE

    json_config = JsonSnapshotConfig(
        out=Path("json"),
        count=2,
        jsonl=True,
        indent=2,
        use_orjson=True,
        shard_size=5,
    )
    json_opts = _build_json_options(json_config)
    assert json_opts.count == 2

    fixtures_config = FixturesSnapshotConfig(
        out=Path("fx"),
        style="function",
        scope="module",
        cases=3,
        return_type="dict",
    )
    fixtures_opts = _build_fixtures_options(fixtures_config)
    assert fixtures_opts.cases == 3

    schema_config = SchemaSnapshotConfig(out=Path("schema"), indent=4)
    schema_opts = _build_schema_options(schema_config)
    assert schema_opts.indent == 4


def test_snapshot_runner_passes_additional_options(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = SnapshotRunner()
    captured: dict[str, Any] = {}

    def fake_diff(**kwargs: Any):
        captured.update(kwargs)
        return [DummyReport(changed=False)]

    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot._execute_diff",
        fake_diff,
    )

    runner.assert_artifacts(
        "models:User",
        json=JsonSnapshotConfig(out=Path("snap.json")),
        respect_validators=True,
        validator_max_retries=5,
        links=("models.User.id=models.Profile.id",),
        rng_mode="portable",
    )

    assert captured["respect_validators"] is True
    assert captured["validator_max_retries"] == 5
    assert captured["links"] == ["models.User.id=models.Profile.id"]
    assert captured["rng_mode"] == "portable"


def test_update_artifacts_invokes_generators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = SnapshotRunner()
    json_calls: dict[str, Any] = {}
    fixtures_calls: dict[str, Any] = {}
    schema_calls: dict[str, Any] = {}

    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot.generate_json",
        lambda **kwargs: json_calls.update(kwargs),
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot.generate_fixtures",
        lambda **kwargs: fixtures_calls.update(kwargs),
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.testing.snapshot.generate_schema",
        lambda **kwargs: schema_calls.update(kwargs),
    )

    runner._update_artifacts(
        target=tmp_path / "models.py",
        json=JsonSnapshotConfig(out=tmp_path / "json.json", count=2, jsonl=True, indent=2),
        fixtures=FixturesSnapshotConfig(out=tmp_path / "fixtures.py", cases=2, scope="function"),
        schema=SchemaSnapshotConfig(out=tmp_path / "schema.json", indent=4),
        include=["models.User"],
        exclude=["models.Admin"],
        seed=123,
        p_none=0.5,
        now="2024-01-01T00:00:00Z",
        preset="boundary",
        profile="pii-safe",
        freeze_seeds=True,
        freeze_seeds_file=tmp_path / "seeds.json",
    )

    assert json_calls["count"] == 2
    assert fixtures_calls["cases"] == 2
    assert schema_calls["indent"] == 4


def test_format_failure_message_without_blocks() -> None:
    message = _format_failure_message([], SnapshotUpdateMode.FAIL)
    assert "Artifacts differ" in message


def test_format_failure_message_with_updates() -> None:
    report = DummyReport(changed=True)
    message = _format_failure_message([report], SnapshotUpdateMode.UPDATE)
    assert "Snapshot update attempted" in message


def test_format_failure_message_skips_unchanged_reports() -> None:
    report = DummyReport(changed=False)
    message = _format_failure_message([report], SnapshotUpdateMode.FAIL)
    assert "Artifacts differ" in message


def test_snapshot_result_changed_flag() -> None:
    report = DummyReport(changed=True)
    result = SnapshotResult(reports=(report,), updated=False, mode=SnapshotUpdateMode.FAIL)
    assert result.changed is True
