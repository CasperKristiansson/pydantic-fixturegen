from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pydantic_fixturegen.cli.gen import app as gen_app

runner = CliRunner()


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel, Field


class Address(BaseModel):
    city: str
    zip_code: str = Field(pattern="^\\d{5}")


class User(BaseModel):
    name: str
    age: int
    address: Address
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_json_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "users.json"

    result = runner.invoke(
        gen_app,
        ["json", str(module_path), "--out", str(output), "--n", "2"],
    )

    assert result.exit_code == 0, result.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    assert "address" in data[0]


def test_gen_json_jsonl_shards(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "samples.jsonl"

    result = runner.invoke(
        gen_app,
        [
            "json",
            str(module_path),
            "--out",
            str(output),
            "--jsonl",
            "--shard-size",
            "2",
            "--n",
            "5",
        ],
    )

    assert result.exit_code == 0, result.stdout
    shard_paths = sorted(tmp_path.glob("samples-*.jsonl"))
    assert len(shard_paths) == 3
    line_counts = [len(path.read_text(encoding="utf-8").splitlines()) for path in shard_paths]
    assert line_counts == [2, 2, 1]


def test_gen_json_respects_config_env(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "compact.json"

    env = {"PFG_JSON__INDENT": "0"}
    result = runner.invoke(
        gen_app,
        ["json", str(module_path), "--out", str(output)],
        env=env,
    )

    assert result.exit_code == 0, result.stdout
    text = output.read_text(encoding="utf-8")
    assert "\n" not in text
