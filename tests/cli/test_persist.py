from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic_fixturegen.api.models import ConfigSnapshot, PersistenceRunResult
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import persist as persist_cli
from pydantic_fixturegen.core.errors import DiscoveryError
from tests._cli import create_cli_runner
from tests.persistence_helpers import SyncCaptureHandler

runner = create_cli_runner()


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
""",
        encoding="utf-8",
    )
    return module_path


def test_persist_with_dotted_handler(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    SyncCaptureHandler.emitted.clear()

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--n",
            "2",
            "--batch-size",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert SyncCaptureHandler.emitted and len(SyncCaptureHandler.emitted[0]) == 1


def test_persist_uses_configured_handler(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.pydantic_fixturegen.persistence.handlers.capture]
path = "tests.persistence_helpers:SyncCaptureHandler"
""",
        encoding="utf-8",
    )
    SyncCaptureHandler.emitted.clear()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "capture",
            "--handler-config",
            '{"marker": "x"}',
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert SyncCaptureHandler.emitted


def test_persist_collection_flags_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)

    captured: dict[str, Any] = {}

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        captured.update(kwargs)
        return PersistenceRunResult(
            handler="capture",
            batches=1,
            records=1,
            retries=0,
            duration=0.1,
            model=type("Model", (), {}),
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
        )

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--collection-min-items",
            "1",
            "--collection-max-items",
            "3",
            "--collection-distribution",
            "max-heavy",
        ],
    )

    assert result.exit_code == 0
    assert captured["collection_min_items"] == 1
    assert captured["collection_max_items"] == 3
    assert captured["collection_distribution"] == "max-heavy"


def test_persist_locale_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    captured: dict[str, Any] = {}

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        captured.update(kwargs)
        return PersistenceRunResult(
            handler="capture",
            batches=1,
            records=1,
            retries=0,
            duration=0.1,
            model=type("Model", (), {}),
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
        )

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--locale",
            "it_IT",
        ],
    )

    assert result.exit_code == 0
    assert captured["locale"] == "it_IT"


def test_persist_locale_map_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    captured: dict[str, Any] = {}

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        captured.update(kwargs)
        return PersistenceRunResult(
            handler="capture",
            batches=1,
            records=1,
            retries=0,
            duration=0.1,
            model=type("Model", (), {}),
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
        )

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--locale-map",
            "*.User=sv_SE",
            "--locale-map",
            "Address.*=en_GB",
        ],
    )

    assert result.exit_code == 0
    assert captured["locale_overrides"] == {"*.User": "sv_SE", "Address.*": "en_GB"}


def test_persist_freeze_and_dry_run_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    captured: dict[str, Any] = {}

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        captured.update(kwargs)
        return PersistenceRunResult(
            handler="dry-run",
            batches=0,
            records=0,
            retries=0,
            duration=0.0,
            model=type("Model", (), {}),
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
        )

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)
    freeze_file = tmp_path / "custom.json"

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--freeze-seeds",
            "--freeze-seeds-file",
            str(freeze_file),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["freeze_seeds"] is True
    assert Path(captured["freeze_seeds_file"]) == freeze_file
    assert captured["dry_run"] is True


def test_persist_with_related_expands_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    captured: dict[str, Any] = {}

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        captured.update(kwargs)
        return PersistenceRunResult(
            handler="capture",
            batches=1,
            records=1,
            retries=0,
            duration=0.1,
            model=type("Model", (), {}),
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
        )

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
            "--with-related",
            "models.Address,models.Company",
            "--with-related",
            "models.Team",
        ],
    )

    assert result.exit_code == 0
    assert captured["with_related"] == ["models.Address", "models.Company", "models.Team"]


def test_persist_handles_pfg_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    raised: list[DiscoveryError] = []

    def fake_persist(**kwargs: Any) -> PersistenceRunResult:
        raise DiscoveryError("boom")

    def fake_render(error: DiscoveryError, *, json_errors: bool, exit_app: bool = True) -> None:
        raised.append(error)

    monkeypatch.setattr("pydantic_fixturegen.cli.persist.persist_samples", fake_persist)
    monkeypatch.setattr(persist_cli.cli_common, "render_cli_error", fake_render)

    result = runner.invoke(
        cli_app,
        [
            "persist",
            str(module_path),
            "--handler",
            "tests.persistence_helpers:SyncCaptureHandler",
        ],
    )

    assert result.exit_code == 0
    assert raised and "boom" in str(raised[0])


def test_parse_handler_config_validates_mapping() -> None:
    assert persist_cli._parse_handler_config('{"debug": true}') == {"debug": True}
    assert persist_cli._parse_handler_config(None) is None
    with pytest.raises(typer.BadParameter):
        persist_cli._parse_handler_config("[]")
