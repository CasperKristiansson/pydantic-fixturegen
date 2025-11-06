from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from typer.testing import CliRunner

MODULE_SOURCE = """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
"""


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")
    return module_path


def test_cli_json_generation_is_deterministic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = CliRunner(mix_stderr=False)

    out1 = tmp_path / "users.json"
    out2 = tmp_path / "users-second.json"

    for output in (out1, out2):
        result = runner.invoke(
            cli_app,
            [
                "gen",
                "json",
                str(module_path),
                "--out",
                str(output),
                "--n",
                "5",
                "--seed",
                "42",
                "--include",
                "models.User",
            ],
        )
        assert result.exit_code == 0, result.stderr

    assert out1.read_bytes() == out2.read_bytes()


def test_cli_schema_generation_is_deterministic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = CliRunner(mix_stderr=False)

    out1 = tmp_path / "schema.json"
    out2 = tmp_path / "schema-second.json"

    for output in (out1, out2):
        result = runner.invoke(
            cli_app,
            [
                "gen",
                "schema",
                str(module_path),
                "--out",
                str(output),
                "--include",
                "models.User",
            ],
        )
        assert result.exit_code == 0, result.stderr

    assert json.loads(out1.read_text(encoding="utf-8")) == json.loads(
        out2.read_text(encoding="utf-8")
    )


def test_cli_fixtures_generation_is_deterministic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    runner = CliRunner(mix_stderr=False)

    out1 = tmp_path / "fixtures.py"
    out2 = tmp_path / "fixtures-second.py"

    for output in (out1, out2):
        result = runner.invoke(
            cli_app,
            [
                "gen",
                "fixtures",
                str(module_path),
                "--out",
                str(output),
                "--seed",
                "123",
                "--include",
                "models.User",
            ],
        )
        assert result.exit_code == 0, result.stderr

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


def test_instance_generation_is_deterministic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    namespace: dict[str, object] = {}
    exec(module_path.read_text(encoding="utf-8"), namespace)  # noqa: S102
    user_cls = cast(type[BaseModel], namespace["User"])

    generator = InstanceGenerator(config=GenerationConfig(seed=99))
    first = generator.generate(user_cls, count=3)

    generator = InstanceGenerator(config=GenerationConfig(seed=99))
    second = generator.generate(user_cls, count=3)

    assert [model.model_dump() for model in first] == [model.model_dump() for model in second]
