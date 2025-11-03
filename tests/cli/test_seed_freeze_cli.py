from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from typer.testing import CliRunner

runner = CliRunner()


def _write_single_model(path: Path, field: str = "value: int") -> None:
    path.write_text(
        f"""
from pydantic import BaseModel


class Sample(BaseModel):
    {field}
""",
        encoding="utf-8",
    )


def test_json_freeze_creates_and_reuses_seeds() -> None:
    with runner.isolated_filesystem():
        module_path = Path("models.py")
        _write_single_model(module_path)

        result = runner.invoke(
            cli_app,
            [
                "gen",
                "json",
                "--freeze-seeds",
                str(module_path),
                "--out",
                "out.json",
            ],
        )

        assert result.exit_code == 0
        assert "Seed freeze entry unavailable" in result.stderr

        freeze_path = Path(".pfg-seeds.json")
        assert freeze_path.is_file()
        first_output = Path("out.json").read_text(encoding="utf-8")
        stored = json.loads(freeze_path.read_text(encoding="utf-8"))
        model_id = "models.Sample"
        stored_seed = stored["models"][model_id]["seed"]
        assert isinstance(stored_seed, int)

        result_second = runner.invoke(
            cli_app,
            [
                "gen",
                "json",
                "--freeze-seeds",
                "--seed",
                "999",
                str(module_path),
                "--out",
                "second.json",
            ],
        )

        assert result_second.exit_code == 0
        assert "Seed freeze entry unavailable" not in result_second.stderr

        second_output = Path("second.json").read_text(encoding="utf-8")
        assert first_output == second_output


def test_json_freeze_warns_on_stale_entry() -> None:
    with runner.isolated_filesystem():
        module_path = Path("models.py")
        _write_single_model(module_path)

        runner.invoke(
            cli_app,
            [
                "gen",
                "json",
                "--freeze-seeds",
                str(module_path),
                "--out",
                "out.json",
            ],
        )

        freeze_path = Path(".pfg-seeds.json")
        initial_payload = json.loads(freeze_path.read_text(encoding="utf-8"))

        _write_single_model(module_path, field="value: int\n    extra: str = 'x'")

        result = runner.invoke(
            cli_app,
            [
                "gen",
                "json",
                "--freeze-seeds",
                str(module_path),
                "--out",
                "out.json",
            ],
        )

        assert result.exit_code == 0
        assert "Seed freeze entry unavailable" in result.stderr

        updated_payload = json.loads(freeze_path.read_text(encoding="utf-8"))
        model_id = "models.Sample"
        assert (
            initial_payload["models"][model_id]["model_digest"]
            != updated_payload["models"][model_id]["model_digest"]
        )


def test_fixtures_freeze_covers_multiple_models() -> None:
    with runner.isolated_filesystem():
        module_path = Path("models.py")
        module_path.write_text(
            """
from pydantic import BaseModel


class Alpha(BaseModel):
    value: int


class Beta(BaseModel):
    name: str
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            cli_app,
            [
                "gen",
                "fixtures",
                "--freeze-seeds",
                str(module_path),
                "--out",
                "fixtures.py",
            ],
        )

        assert result.exit_code == 0
        assert "Seed freeze entry unavailable" in result.stderr

        freeze_path = Path(".pfg-seeds.json")
        payload = json.loads(freeze_path.read_text(encoding="utf-8"))
        seeds = payload["models"]
        assert "models.Alpha" in seeds
        assert "models.Beta" in seeds

        first_output = Path("fixtures.py").read_text(encoding="utf-8")

        result_second = runner.invoke(
            cli_app,
            [
                "gen",
                "fixtures",
                "--freeze-seeds",
                "--seed",
                "321",
                str(module_path),
                "--out",
                "fixtures_second.py",
            ],
        )

        assert result_second.exit_code == 0
        second_output = Path("fixtures_second.py").read_text(encoding="utf-8")
        assert first_output == second_output
