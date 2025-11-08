from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

pytest.importorskip("hypothesis")
from hypothesis.errors import NonInteractiveExampleWarning

MODULE_SOURCE = """
from pydantic import BaseModel, Field


class User(BaseModel):
    email: str
    age: int = Field(ge=1)


class Order(BaseModel):
    total: float
"""


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")
    return module_path


def test_gen_strategies_writes_module(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output_path = tmp_path / "strategies.py"
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--out",
            str(output_path),
            "--include",
            "models.User",
            "--seed",
            "7",
            "--strategy-profile",
            "edge",
        ],
    )

    assert result.exit_code == 0, result.output
    content = output_path.read_text(encoding="utf-8")
    assert "strategy_for" in content

    import sys

    sys.modules.pop("models", None)
    sys.path.insert(0, str(tmp_path))
    try:
        module_globals = runpy.run_path(output_path)
    finally:
        sys.path.remove(str(tmp_path))
    strategy = module_globals.get("models_user_strategy")
    assert strategy is not None
    with pytest.warns(NonInteractiveExampleWarning):
        example = strategy.example()
    assert example.email
