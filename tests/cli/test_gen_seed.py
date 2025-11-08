from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

try:  # pragma: no cover - optional dependencies
    from mongomock_motor import AsyncMongoMockClient
    from sqlalchemy import text
    from sqlmodel import create_engine
except ModuleNotFoundError:  # pragma: no cover - optional dependencies
    pytest.skip("sqlmodel and mongomock_motor are required", allow_module_level=True)

pytest.importorskip("beanie")

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_sqlmodel_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "sql_models.py"
    module_path.write_text(
        """
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_seed_sqlmodel_inserts_rows(tmp_path: Path) -> None:
    module_path = _write_sqlmodel_module(tmp_path)
    database_path = tmp_path / "seed.db"
    database_url = f"sqlite:///{database_path}"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "sqlmodel",
            str(module_path),
            "--database",
            database_url,
            "--include",
            "sql_models.User",
            "--n",
            "3",
            "--create-schema",
        ],
    )

    if result.exit_code != 0:  # pragma: no cover - diagnostic
        print(result.output)

    assert result.exit_code == 0, result.output

    engine = create_engine(database_url)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM user")).scalar_one()
        assert count == 3
    engine.dispose()


def test_gen_seed_sqlmodel_rollback(tmp_path: Path) -> None:
    module_path = _write_sqlmodel_module(tmp_path)
    database_path = tmp_path / "seed.db"
    database_url = f"sqlite:///{database_path}"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "sqlmodel",
            str(module_path),
            "--database",
            database_url,
            "--include",
            "sql_models.User",
            "--n",
            "2",
            "--create-schema",
            "--truncate",
            "--rollback",
        ],
    )

    assert result.exit_code == 0, result.stdout

    engine = create_engine(database_url)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM user")).scalar_one()
        assert count == 0
    engine.dispose()


def _write_beanie_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "beanie_models.py"
    module_path.write_text(
        """
from beanie import Document


class Account(Document):
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_seed_beanie_inserts_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_beanie_module(tmp_path)
    database_url = "mongodb://example.com/mockdb"
    fake_client = AsyncMongoMockClient()

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.seed._create_beanie_client",
        lambda _: fake_client,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "beanie",
            str(module_path),
            "--database",
            database_url,
            "--include",
            "beanie_models.Account",
            "--n",
            "2",
        ],
    )

    assert result.exit_code == 0, result.stdout

    async def _fetch() -> int:
        database = fake_client["mockdb"]
        names = await database.list_collection_names()
        total = 0
        for name in names:
            cursor = database[name].find({})
            total += len([doc async for doc in cursor])
        return total

    count = asyncio.run(_fetch())
    assert count == 2
