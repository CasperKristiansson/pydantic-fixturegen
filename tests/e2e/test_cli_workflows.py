from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.testing import (
    JsonSnapshotConfig,
    SnapshotAssertionError,
    SnapshotRunner,
)
from tests._cli import create_cli_runner

BASIC_MODULE = """
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int
"""

SCHEMA_MODULE = """
from pydantic import BaseModel


class User(BaseModel):
    id: int


class Order(BaseModel):
    total: float
"""


def _write_module(tmp_path: Path, source: str, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(source, encoding="utf-8")
    return module_path


def test_gen_json_with_freeze_seeds_is_stable(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, BASIC_MODULE)
    runner = create_cli_runner()
    output = tmp_path / "snapshots" / "user.json"
    freeze_file = tmp_path / "custom-freeze.json"

    first = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
            "--n",
            "2",
            "--seed",
            "777",
            "--freeze-seeds",
            "--freeze-seeds-file",
            str(freeze_file),
        ],
    )
    assert first.exit_code == 0, first.output
    snapshot_bytes = output.read_bytes()
    assert freeze_file.exists()

    output.unlink()

    second = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
            "--n",
            "2",
            "--freeze-seeds",
            "--freeze-seeds-file",
            str(freeze_file),
        ],
    )
    assert second.exit_code == 0, second.output
    assert output.read_bytes() == snapshot_bytes


def test_schema_generation_with_templates(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, SCHEMA_MODULE, name="domain")
    runner = create_cli_runner()
    schema_template = tmp_path / "schemas" / "{model}.json"

    for include_pattern in ("domain.User", "domain.Order"):
        result = runner.invoke(
            cli_app,
            [
                "gen",
                "schema",
                str(module_path),
                "--out",
                str(schema_template),
                "--include",
                include_pattern,
                "--indent",
                "0",
                "--profile",
                "realistic",
            ],
        )
        assert result.exit_code == 0, result.output

    user_schema = (tmp_path / "schemas" / "User.json").read_text(encoding="utf-8")
    order_schema = (tmp_path / "schemas" / "Order.json").read_text(encoding="utf-8")
    assert json.loads(user_schema)["title"] == "User"
    assert json.loads(order_schema)["title"] == "Order"


def test_check_reports_json_error_payload() -> None:
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        ["check", "--json-errors", "missing_module.py"],
        catch_exceptions=False,
    )
    assert result.exit_code == 10
    payload = json.loads(result.stdout)
    assert payload["error"]["kind"] == "DiscoveryError"


def test_snapshot_runner_validates_cli_snapshots(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, BASIC_MODULE)
    runner = create_cli_runner()
    snapshot_path = tmp_path / "snapshots" / "user.json"

    gen_result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(snapshot_path),
            "--include",
            "models.User",
            "--seed",
            "404",
        ],
    )
    assert gen_result.exit_code == 0, gen_result.output

    runner_helper = SnapshotRunner()
    config = JsonSnapshotConfig(out=snapshot_path, indent=2)
    runner_helper.assert_artifacts(
        target=module_path,
        json=config,
        include=["models.User"],
        seed=404,
    )

    snapshot_path.write_text("[]", encoding="utf-8")

    with pytest.raises(SnapshotAssertionError):
        runner_helper.assert_artifacts(
            target=module_path,
            json=config,
            include=["models.User"],
            seed=404,
        )
