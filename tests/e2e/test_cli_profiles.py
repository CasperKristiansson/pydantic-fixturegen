from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

SENSITIVE_MODULE = """
from pydantic import BaseModel, AnyUrl


class Contact(BaseModel):
    site: AnyUrl
"""

MULTI_MODEL_SOURCE = """
from pydantic import BaseModel


class User(BaseModel):
    email: str
    age: int


class Ignored(BaseModel):
    flag: bool
"""


def _write_module(tmp_path: Path, name: str, source: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(source, encoding="utf-8")
    return module_path


def test_gen_json_profile_pii_safe_masks_sensitive_fields(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, "contacts", SENSITIVE_MODULE)
    runner = create_cli_runner()
    output = tmp_path / "contact_fixtures.py"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "contacts.Contact",
            "--seed",
            "13",
            "--profile",
            "pii-safe",
        ],
    )
    assert result.exit_code == 0, result.output

    content = output.read_text(encoding="utf-8")
    assert "example.invalid" in content


def test_profiles_change_fixture_outputs(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, "contacts", SENSITIVE_MODULE)
    runner = create_cli_runner()
    safe_out = tmp_path / "safe.py"
    default_out = tmp_path / "default.py"

    safe_result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(safe_out),
            "--include",
            "contacts.Contact",
            "--seed",
            "21",
            "--profile",
            "pii-safe",
        ],
    )
    assert safe_result.exit_code == 0, safe_result.output

    default_result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module_path),
            "--out",
            str(default_out),
            "--include",
            "contacts.Contact",
            "--seed",
            "21",
        ],
    )
    assert default_result.exit_code == 0, default_result.output

    safe_content = safe_out.read_text(encoding="utf-8")
    default_content = default_out.read_text(encoding="utf-8")
    assert safe_content != default_content
    assert "example.invalid" in safe_content
    assert "example.invalid" not in default_content


def test_json_command_supports_many_flags(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, "inventory", MULTI_MODEL_SOURCE)
    runner = create_cli_runner()
    output_base = tmp_path / "samples.jsonl"
    freeze_file = tmp_path / "custom-seeds.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output_base),
            "--jsonl",
            "--n",
            "3",
            "--shard-size",
            "2",
            "--indent",
            "0",
            "--orjson",
            "--seed",
            "314",
            "--freeze-seeds",
            "--freeze-seeds-file",
            str(freeze_file),
            "--include",
            "inventory.User",
            "--exclude",
            "inventory.Ignored",
            "--preset",
            "boundary",
            "--profile",
            "realistic",
        ],
    )
    assert result.exit_code == 0, result.output

    shard_paths = sorted(tmp_path.glob("samples*.jsonl"))
    assert len(shard_paths) == 2

    rows: list[dict[str, object]] = []
    for shard in shard_paths:
        for line in shard.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    assert len(rows) == 3
    assert all("flag" not in row for row in rows)
    assert all(isinstance(row["email"], str) for row in rows)
    assert freeze_file.exists()
