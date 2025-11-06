from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.testing import snapshot


def test_normalize_patterns_trims_and_joins() -> None:
    assert snapshot._normalize_patterns(None) is None  # type: ignore[attr-defined]
    assert snapshot._normalize_patterns(["", "  "]) is None  # type: ignore[attr-defined]
    assert (
        snapshot._normalize_patterns([" foo ", "bar "])  # type: ignore[attr-defined]
        == "foo,bar"
    )


def test_build_option_helpers_return_defaults(tmp_path: Path) -> None:
    json_opts = snapshot._build_json_options(None)  # type: ignore[attr-defined]
    assert json_opts.count == 1 and json_opts.out is None

    fixtures_opts = snapshot._build_fixtures_options(None)  # type: ignore[attr-defined]
    assert fixtures_opts.cases == 1 and fixtures_opts.out is None

    schema_opts = snapshot._build_schema_options(None)  # type: ignore[attr-defined]
    assert schema_opts.indent is None and schema_opts.out is None

    cfg = snapshot.JsonSnapshotConfig(out=tmp_path / "data.json", count=2, jsonl=True)
    built = snapshot._build_json_options(cfg)  # type: ignore[attr-defined]
    assert built.out == cfg.out and built.jsonl is True


def test_snapshot_runner_handles_no_differences(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = snapshot.SnapshotRunner()

    monkeypatch.setattr(
        snapshot,
        "_execute_diff",
        lambda **_: [SimpleNamespace(changed=False)],
    )

    runner.assert_artifacts(
        target="module.Model",
        json=snapshot.JsonSnapshotConfig(out=Path("snapshot.json")),
    )


def test_snapshot_runner_updates_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = snapshot.SnapshotRunner(update_mode=snapshot.SnapshotUpdateMode.UPDATE)
    reports = [
        SimpleNamespace(
            changed=True,
            kind="json",
            target="snapshot.json",
            messages=["mismatch"],
            diff_outputs=[("path", "---")],
            summary="summary",
        )
    ]
    call_sequence: list[str] = []

    def fake_execute_diff(**_: object):
        call_sequence.append("diff")
        if len(call_sequence) == 1:
            return reports
        return [SimpleNamespace(changed=False)]

    monkeypatch.setattr(snapshot, "_execute_diff", fake_execute_diff)

    def fake_update(self, **_: object) -> None:
        call_sequence.append("update")

    monkeypatch.setattr(snapshot.SnapshotRunner, "_update_artifacts", fake_update)

    runner.assert_artifacts(
        target="module.Model",
        json=snapshot.JsonSnapshotConfig(out=Path("snapshot.json")),
    )

    assert call_sequence == ["diff", "update", "diff"]


def test_snapshot_runner_raises_failure_message(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = snapshot.SnapshotRunner()
    failure_report = SimpleNamespace(
        changed=True,
        kind="json",
        target="snapshot.json",
        messages=["expected foo"],
        diff_outputs=[("snapshot.json", "---expected")],
        summary="1 differences",
    )

    monkeypatch.setattr(snapshot, "_execute_diff", lambda **_: [failure_report])

    with pytest.raises(snapshot.SnapshotAssertionError) as exc_info:
        runner.assert_artifacts(
            target="module.Model",
            json=snapshot.JsonSnapshotConfig(out=Path("snapshot.json")),
        )

    message = str(exc_info.value)
    assert "json mismatch for snapshot.json" in message
    assert "Run again with update" in message


def test_snapshot_runner_update_invokes_generators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = snapshot.SnapshotRunner()
    target = tmp_path / "models.py"
    target.write_text("placeholder", encoding="utf-8")

    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        snapshot,
        "generate_json",
        lambda **kwargs: calls.append(("json", kwargs)),
    )
    monkeypatch.setattr(
        snapshot,
        "generate_fixtures",
        lambda **kwargs: calls.append(("fixtures", kwargs)),
    )
    monkeypatch.setattr(
        snapshot,
        "generate_schema",
        lambda **kwargs: calls.append(("schema", kwargs)),
    )

    json_cfg = snapshot.JsonSnapshotConfig(
        out=tmp_path / "data.json",
        count=2,
        jsonl=True,
        indent=0,
        shard_size=1,
    )
    fixtures_cfg = snapshot.FixturesSnapshotConfig(
        out=tmp_path / "tests/test_models.py",
        style="factory",
        scope="module",
        cases=2,
        return_type="dict",
    )
    schema_cfg = snapshot.SchemaSnapshotConfig(out=tmp_path / "schema.json", indent=4)

    runner._update_artifacts(
        target=target,
        json=json_cfg,
        fixtures=fixtures_cfg,
        schema=schema_cfg,
        include=[" models.User "],
        exclude=[" tests.* "],
        seed=42,
        p_none=0.25,
        now="2024-01-01T00:00:00Z",
        preset="boundary",
        freeze_seeds=True,
        freeze_seeds_file=tmp_path / "freeze.json",
    )

    kinds = [kind for kind, _ in calls]
    assert kinds == ["json", "fixtures", "schema"]
    json_call = calls[0][1]
    assert json_call["jsonl"] is True
    assert tuple(value.strip() for value in json_call["include"]) == ("models.User",)
    fixtures_call = calls[1][1]
    assert fixtures_call["style"] == "factory"
    schema_call = calls[2][1]
    assert schema_call["indent"] == 4
