from __future__ import annotations

from pathlib import Path

import pytest
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

    assert result.exit_code == 0, result.stdout
    content = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "id,name,__cycles__"
    assert len(content) == 3


def test_gen_dataset_parquet(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow.parquet")
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

    import pyarrow.parquet as pq  # noqa: PLC0415

    table = pq.read_table(output_path)
    assert table.num_rows == 2


def test_gen_dataset_arrow(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    pytest.importorskip("pyarrow.ipc")

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

    import pyarrow.ipc as ipc  # noqa: PLC0415

    with ipc.open_file(output_path) as reader:
        assert reader.read_all().num_rows == 2
