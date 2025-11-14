from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("polyfactory")

from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.polyfactory_support.discovery import (
    POLYFACTORY_MODEL_FACTORY,
    POLYFACTORY_UNAVAILABLE_REASON,
)
from tests._cli import create_cli_runner

runner = create_cli_runner()


def test_polyfactory_migrate_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "models_poly.py"
    module_path.write_text(
        """
from pydantic import BaseModel
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use, Ignore


def slugify(prefix: str) -> str:
    return f"{prefix}-slug"


class Model(BaseModel):
    slug: str
    alias: str | None = None


class ModelFactoryShim(ModelFactory[Model]):
    __model__ = Model
    __check_model__ = False
    slug = Use(slugify, "fixture")
    alias = Ignore()
""",
        encoding="utf-8",
    )

    overrides_path = tmp_path / "overrides.toml"
    if POLYFACTORY_MODEL_FACTORY is None and POLYFACTORY_UNAVAILABLE_REASON:
        pytest.skip(POLYFACTORY_UNAVAILABLE_REASON)
    result = runner.invoke(
        cli_app,
        [
            "polyfactory",
            "migrate",
            str(module_path),
            "--format",
            "json",
            "--overrides-out",
            str(overrides_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload and payload[0]["fields"]
    override_text = overrides_path.read_text(encoding="utf-8")
    assert "polyfactory_support.migration_helpers" in override_text
    assert "slug" in override_text
