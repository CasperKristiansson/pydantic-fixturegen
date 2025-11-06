from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner(mix_stderr=False)


def test_list_invalid_path_json_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(cli_app, ["list", "--json-errors", str(missing)])

    assert result.exit_code == 10
    payload = json.loads(result.stdout)
    assert payload["error"]["kind"] == "DiscoveryError"
    assert payload["error"]["details"]["path"].endswith("missing.py")


def test_gen_json_multiple_models_error(tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Foo(BaseModel):
    value: int


class Bar(BaseModel):
    label: str
""",
        encoding="utf-8",
    )
    output = tmp_path / "out.json"

    result = runner.invoke(
        cli_app,
        ["gen", "json", str(module), "--out", str(output), "--n", "1", "--json-errors"],
    )

    assert result.exit_code == 10
    payload = json.loads(result.stdout)
    assert payload["error"]["kind"] == "DiscoveryError"
    assert "Multiple models" in payload["error"]["message"]


def test_gen_fixtures_invalid_style(tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Foo(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    output = tmp_path / "fixtures.py"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "fixtures",
            str(module),
            "--out",
            str(output),
            "--style",
            "invalid",
            "--json-errors",
        ],
    )

    assert result.exit_code == 10
    payload = json.loads(result.stdout)
    assert payload["error"]["kind"] == "DiscoveryError"
    assert "Invalid style" in payload["error"]["message"]
