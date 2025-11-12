from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.ipc as pa_ipc
import pyarrow.parquet as pq
import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot, DatasetGenerationResult
from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_models(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_dataset_csv(tmp_path: Path) -> None:
    module_path = _write_models(tmp_path)
    output_path = tmp_path / "users.csv"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(output_path),
            "--format",
            "csv",
            "--n",
            "2",
        ],
    )

    assert result.exit_code == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    content = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "id,name,__cycles__"
    assert len(content) == 3


def test_gen_dataset_parquet(tmp_path: Path) -> None:
    module_path = _write_models(tmp_path)
    output_path = tmp_path / "users.parquet"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(output_path),
            "--format",
            "parquet",
            "--n",
            "2",
        ],
    )

    assert result.exit_code == 0, result.stdout

    table = pq.read_table(output_path)
    assert table.num_rows == 2


def test_gen_dataset_arrow(tmp_path: Path) -> None:
    module_path = _write_models(tmp_path)
    output_path = tmp_path / "users.arrow"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(output_path),
            "--format",
            "arrow",
            "--n",
            "2",
        ],
    )

    assert result.exit_code == 0, result.stdout

    with pa_ipc.open_file(output_path) as reader:
        assert reader.read_all().num_rows == 2


def test_gen_dataset_supports_typeddict_models(tmp_path: Path) -> None:
    module_path = tmp_path / "typed_models.py"
    module_path.write_text(
        """
from typing import TypedDict


class Audit(TypedDict):
    level: str
    actor: str


class Event(TypedDict):
    name: str
    audit: Audit
""",
        encoding="utf-8",
    )
    output_path = tmp_path / "events.csv"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(output_path),
            "--format",
            "csv",
            "--n",
            "1",
            "--include",
            "typed_models.Event",
        ],
    )

    assert result.exit_code == 0, result.stdout
    rows = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert rows[0].startswith("name,audit")


def test_gen_dataset_field_hints_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_models(tmp_path)
    output_path = tmp_path / "users.csv"

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> DatasetGenerationResult:
        captured.update(kwargs)
        return DatasetGenerationResult(
            paths=(output_path,),
            base_output=output_path,
            model=None,  # type: ignore[arg-type]
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            warnings=(),
            constraint_summary=None,
            delegated=False,
            format="csv",
        )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.generate_dataset_artifacts",
        fake_generate,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(output_path),
            "--field-hints",
            "defaults-then-examples",
        ],
    )

    assert result.exit_code == 0
    assert captured["field_hints"] == "defaults-then-examples"
