from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import diff as diff_mod
from pydantic_fixturegen.cli.diff import (
    DiffReport,
    FixturesDiffOptions,
    JsonDiffOptions,
    SchemaDiffOptions,
    _execute_diff,
    _render_reports,
    _resolve_method,
)
from pydantic_fixturegen.core.config import AppConfig
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.seed_freeze import FREEZE_FILE_BASENAME
from tests._cli import create_cli_runner

runner = create_cli_runner()


class FakeLogger:
    def __init__(self) -> None:
        self.warn_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.config = SimpleNamespace(json=False)

    def warn(self, message: str, **kwargs: object) -> None:
        self.warn_calls.append((message, kwargs))

    def info(self, message: str, **kwargs: object) -> None:
        self.info_calls.append((message, kwargs))


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def test_diff_json_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "products.json"

    gen_result = runner.invoke(
        cli_app,
        ["gen", "json", str(module_path), "--out", str(json_out), "--n", "2", "--seed", "123"],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "2",
            "--seed",
            "123",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "JSON artifacts match" in diff_result.stdout


def test_diff_json_detects_changes(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "products.json"

    runner.invoke(
        cli_app,
        ["gen", "json", str(module_path), "--out", str(json_out), "--n", "1", "--seed", "42"],
    )

    json_out.write_text("[]\n", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "1",
            "--seed",
            "42",
            "--show-diff",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "JSON differences detected" in diff_result.stdout
    assert "@@" in diff_result.stdout  # unified diff marker


def test_diff_json_errors_payload(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing_json = tmp_path / "artifacts" / "missing.json"

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-errors",
            "--json-out",
            str(missing_json),
            str(module_path),
        ],
    )

    assert result.exit_code == 50
    assert "DiffError" in result.stdout
    assert "Missing JSON artifact" in result.stdout


def test_diff_cli_forwards_validator_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "artifacts" / "products.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text("[]\n", encoding="utf-8")

    captured: dict[str, Any] = {}

    report = DiffReport(
        kind="json",
        target=json_out,
        checked_paths=[json_out],
        messages=[],
        diff_outputs=[],
        summary="ok",
        constraint_report=None,
    )

    def fake_execute(**kwargs: Any) -> list[DiffReport]:
        captured.update(kwargs)
        return [report]

    monkeypatch.setattr("pydantic_fixturegen.cli.diff._execute_diff", fake_execute)

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--respect-validators",
            "--validator-max-retries",
            "6",
            str(module_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["respect_validators"] is True
    assert captured["validator_max_retries"] == 6


def test_diff_fixtures_missing_file(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    fixtures_out = tmp_path / "fixtures" / "test_products.py"

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--fixtures-out",
            str(fixtures_out),
            str(module_path),
        ],
    )

    assert result.exit_code == 1
    assert "Missing fixtures module" in result.stdout


def test_diff_json_reports_extra_file(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    json_dir = tmp_path / "artifacts"
    json_dir.mkdir()
    json_out = json_dir / "products.json"

    runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(json_out),
            "--n",
            "2",
            "--seed",
            "7",
            "--shard-size",
            "1",
        ],
    )

    extra = json_dir / "products-999.json"
    extra.write_text("[]", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-count",
            "2",
            "--json-shard-size",
            "1",
            "--seed",
            "7",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "Unexpected extra JSON artifact" in diff_result.stdout


def test_diff_schema_detects_drift(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    schema_out = tmp_path / "schema" / "product.json"

    runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(schema_out),
        ],
    )

    schema_out.write_text("{}", encoding="utf-8")

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--schema-out",
            str(schema_out),
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 1
    assert "Schema artifact differs" in diff_result.stdout


def test_diff_handles_internal_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "missing.json"

    def raise_discovery(**_: object) -> list[DiffReport]:
        raise DiscoveryError("broken")

    monkeypatch.setattr("pydantic_fixturegen.cli.diff._execute_diff", raise_discovery)

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-out",
            str(json_out),
            "--json-errors",
            str(module_path),
        ],
    )

    assert result.exit_code == 10
    assert "broken" in result.stdout


def test_diff_json_errors_payload_on_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    json_out = tmp_path / "existing.json"
    json_out.write_text("[]", encoding="utf-8")

    report = DiffReport(
        kind="json",
        target=json_out,
        checked_paths=[json_out],
        messages=["diff"],
        diff_outputs=[(str(json_out), "---")],
        summary=None,
        constraint_report={"fields": 1},
        time_anchor="2024-01-01T00:00:00+00:00",
    )

    monkeypatch.setattr("pydantic_fixturegen.cli.diff._execute_diff", lambda **_: [report])

    result = runner.invoke(
        cli_app,
        [
            "diff",
            "--json-errors",
            "--json-out",
            str(json_out),
            str(module_path),
        ],
    )

    assert result.exit_code == 50
    assert '"kind": "json"' in result.stdout


def test_execute_diff_freeze_seed_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    freeze_file = tmp_path / FREEZE_FILE_BASENAME
    freeze_file.write_text("{invalid", encoding="utf-8")

    include_patterns = "models.Product"
    logger = FakeLogger()
    captured_warnings: list[str] = []
    monkeypatch.setattr(diff_mod, "get_logger", lambda: logger)
    monkeypatch.setattr(diff_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(diff_mod, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(
        diff_mod.typer,
        "secho",
        lambda message, **kwargs: captured_warnings.append(str(message)),
    )

    app_config = AppConfig(
        include=(include_patterns,),
        exclude=(),
        seed=123,
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(diff_mod, "load_config", lambda root, cli=None: app_config)

    class DemoModel(BaseModel):
        name: str

    discovery_result = SimpleNamespace(
        models=[SimpleNamespace(module="models", qualname="Product")],
        warnings=[" stale freeze "],
        errors=[],
    )
    monkeypatch.setattr(diff_mod, "discover_models", lambda *args, **kwargs: discovery_result)
    monkeypatch.setattr(diff_mod, "load_model_class", lambda info: DemoModel)

    diff_report = DiffReport(
        kind="json",
        target=tmp_path / "products.json",
        checked_paths=[],
        messages=[],
        diff_outputs=[],
        summary="JSON artifacts match",
        constraint_report={"fields": 1},
        time_anchor="2024-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(diff_mod, "_diff_json_artifact", lambda **kwargs: diff_report)
    reports = _execute_diff(
        target=str(module_path),
        include=include_patterns,
        exclude=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=5.0,
        memory_limit_mb=128,
        seed_override=None,
        p_none_override=None,
        json_options=JsonDiffOptions(
            out=tmp_path / "products.json",
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
        ),
        fixtures_options=FixturesDiffOptions(
            out=None,
            style=None,
            scope=None,
            cases=1,
            return_type=None,
        ),
        schema_options=SchemaDiffOptions(out=None, indent=None),
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
        preset="boundary",
        now_override="2024-02-01T00:00:00Z",
    )

    assert reports and reports[0].summary == "JSON artifacts match"
    assert any(call[1]["event"] == "seed_freeze_invalid" for call in logger.warn_calls)
    assert any(call[1]["event"] == "seed_freeze_missing" for call in logger.warn_calls)
    assert any("stale freeze" in warning for warning in captured_warnings)
    assert logger.info_calls and logger.info_calls[0][1]["event"] == "temporal_anchor_set"


def test_execute_diff_requires_artifact_option(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    with pytest.raises(DiscoveryError):
        _execute_diff(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
            seed_override=None,
            p_none_override=None,
            json_options=JsonDiffOptions(
                out=None,
                count=1,
                jsonl=False,
                indent=None,
                use_orjson=None,
                shard_size=None,
            ),
            fixtures_options=FixturesDiffOptions(
                out=None,
                style=None,
                scope=None,
                cases=1,
                return_type=None,
            ),
            schema_options=SchemaDiffOptions(out=None, indent=None),
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            now_override=None,
        )


def test_render_reports_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        diff_mod.typer,
        "secho",
        lambda message="", **kwargs: captured.append(str(message)),
    )
    monkeypatch.setattr(
        diff_mod.typer,
        "echo",
        lambda message="": captured.append(str(message)),
    )

    logger = FakeLogger()
    _render_reports([], show_diff=False, logger=logger, json_mode=False)
    assert captured[-1] == "No artifacts were compared."

    captured.clear()
    unchanged = DiffReport(
        kind="json",
        target=Path("a.json"),
        checked_paths=[],
        messages=[],
        diff_outputs=[],
        summary="JSON artifacts match.",
        constraint_report=None,
        time_anchor=None,
    )
    with_diffs = DiffReport(
        kind="fixtures",
        target=Path("fixtures.py"),
        checked_paths=[],
        messages=["Missing fixture"],
        diff_outputs=[("fixtures.py", "---diff---")],
        summary=None,
        constraint_report={"issues": []},
        time_anchor="2024-01-01T00:00:00+00:00",
    )
    _render_reports([unchanged, with_diffs], show_diff=True, logger=logger, json_mode=False)
    assert "All compared artifacts match." not in captured  # because a change existed
    assert any("Missing fixture" in entry for entry in captured)
    assert "---diff---" in captured
    assert logger.warn_calls == []  # render doesn't use logger.warn


def test_resolve_method_validation() -> None:
    assert _resolve_method(False, False) == "import"
    assert _resolve_method(True, False) == "ast"
    assert _resolve_method(False, True) == "hybrid"
    with pytest.raises(DiscoveryError):
        _resolve_method(True, True)


def test_diff_fixtures_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    fixtures_out = tmp_path / "fixtures" / "test_products.py"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(fixtures_out),
            "--seed",
            "123",
        ],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--fixtures-out",
            str(fixtures_out),
            "--seed",
            "123",
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "Fixtures artifact matches" in diff_result.stdout


def test_diff_schema_matches(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    schema_out = tmp_path / "schema" / "product.json"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(schema_out),
        ],
    )
    assert gen_result.exit_code == 0

    diff_result = runner.invoke(
        cli_app,
        [
            "diff",
            "--schema-out",
            str(schema_out),
            str(module_path),
        ],
    )

    assert diff_result.exit_code == 0
    assert "Schema artifact matches" in diff_result.stdout
