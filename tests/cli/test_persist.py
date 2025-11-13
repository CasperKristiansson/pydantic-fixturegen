from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot, PersistenceRunResult
from pydantic_fixturegen.cli import app as cli_app
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
            "{\"marker\": \"x\"}",
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
