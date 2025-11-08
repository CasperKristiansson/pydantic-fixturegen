from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def test_gen_polyfactory_exports_factories(tmp_path: Path) -> None:
    pytest.importorskip("polyfactory")

    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
""",
        encoding="utf-8",
    )

    output_path = tmp_path / "factories.py"
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
            "--out",
            str(output_path),
            "--seed",
            "7",
        ],
    )

    assert result.exit_code == 0, result.stdout

    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("factories")
        assert hasattr(module, "UserFactory")
        factory = module.UserFactory
        instance = factory.build()
        assert instance.name
        module.seed_factories(13)
        second = factory.build()
        assert second.name
    finally:
        sys.path.pop(0)
        if "factories" in sys.modules:
            del sys.modules["factories"]
