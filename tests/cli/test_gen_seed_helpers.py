from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import seed as seed_cli
from pydantic_fixturegen.cli.gen.seed import (
    _mongo_database_name,
    _resolve_target_module,
    _validate_connection,
)
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError
from tests._cli import create_cli_runner


def test_validate_connection_allows_known_prefix() -> None:
    _validate_connection("sqlite:///tmp.db", ["sqlite://", "postgres://"])


def test_validate_connection_rejects_unknown_prefix() -> None:
    with pytest.raises(DiscoveryError):
        _validate_connection("mysql://localhost/db", ["sqlite://"])


def test_mongo_database_name_requires_path() -> None:
    assert _mongo_database_name("mongodb://localhost/appdb") == "appdb"
    with pytest.raises(DiscoveryError):
        _mongo_database_name("mongodb://localhost/")


def test_resolve_target_module_accepts_module_path(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\n"
        "class Model(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )

    resolved = _resolve_target_module(str(module_path), schema=None)
    assert resolved == module_path.resolve()


def test_resolve_target_module_rejects_missing_inputs(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")

    with pytest.raises(DiscoveryError):
        _resolve_target_module(None, None)

    with pytest.raises(DiscoveryError):
        _resolve_target_module(str(tmp_path / "models.py"), schema_path)

    missing_schema = tmp_path / "missing.json"
    with pytest.raises(DiscoveryError):
        _resolve_target_module(None, missing_schema)


def test_resolve_target_module_ingests_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    generated = tmp_path / "generated.py"

    class DummyIngester:
        def ingest_json_schema(self, path: Path) -> SimpleNamespace:
            assert path == schema_path.resolve()
            return SimpleNamespace(path=generated)

    monkeypatch.setattr(seed_cli, "SchemaIngester", DummyIngester)
    resolved = _resolve_target_module(None, schema_path)
    assert resolved == generated


def test_create_plan_expands_with_related(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text("pass", encoding="utf-8")
    recorded: dict[str, object] = {}

    def fake_builder(**kwargs: object) -> str:
        recorded.update(kwargs)
        return "plan"

    monkeypatch.setattr(seed_cli, "_build_model_artifact_plan", fake_builder)

    plan = seed_cli._create_plan(
        module_path=module_path,
        include=None,
        exclude=None,
        seed=None,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        profile=None,
        respect_validators=None,
        validator_max_retries=None,
        links=None,
        with_related=["models.Related"],
        max_depth=None,
        cycle_policy=None,
        rng_mode=None,
        logger=seed_cli.get_logger(),
    )

    assert plan == "plan"
    assert recorded["with_related"] == ["models.Related"]


def test_validate_connection_skips_when_allowlist_empty() -> None:
    _validate_connection("anything", [])


def _suppress_seed_cli_exit(monkeypatch: pytest.MonkeyPatch) -> list[DiscoveryError]:
    original_render = seed_cli.render_cli_error
    captured: list[DiscoveryError] = []

    def patched(error: DiscoveryError, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original_render(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(seed_cli, "render_cli_error", patched)
    return captured


def test_seed_sqlmodel_cli_runs_with_stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = create_cli_runner()
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\nclass Model(BaseModel):\n    value: int\n",
        encoding="utf-8",
    )
    recorded: dict[str, object] = {}

    monkeypatch.setattr(seed_cli, "_resolve_target_module", lambda target, schema: module_path)
    monkeypatch.setattr(seed_cli, "_create_plan", lambda **kwargs: "plan")

    def fake_factory(
        database: str,
        *,
        echo: bool,
        create_schema: bool,
    ) -> tuple[callable, callable]:
        recorded["factory"] = (database, echo, create_schema)

        def dispose() -> None:
            recorded["disposed"] = True

        return (lambda: None, dispose)

    monkeypatch.setattr(seed_cli, "_build_sqlmodel_session_factory", fake_factory)

    class DummySeeder:
        def __init__(self, plan: object, session_factory: callable, logger: object) -> None:
            recorded["plan"] = plan

        def seed(
            self,
            *,
            count: int,
            batch_size: int,
            rollback: bool,
            dry_run: bool,
            truncate: bool,
        ) -> SimpleNamespace:
            recorded["seed_args"] = {
                "count": count,
                "batch_size": batch_size,
                "rollback": rollback,
                "dry_run": dry_run,
                "truncate": truncate,
            }
            return SimpleNamespace(inserted=count, rollback=rollback, dry_run=dry_run)

    monkeypatch.setattr("pydantic_fixturegen.orm.sqlalchemy.SQLAlchemySeeder", DummySeeder)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "sqlmodel",
            str(module_path),
            "--database",
            "sqlite:///tmp.db",
            "--dry-run",
            "--rollback",
            "--batch-size",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert recorded["seed_args"]["dry_run"] is True
    assert recorded.get("disposed") is True


def test_seed_beanie_cli_runs_with_stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = create_cli_runner()
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\nclass Doc(BaseModel):\n    value: int\n",
        encoding="utf-8",
    )
    recorded: dict[str, object] = {}

    monkeypatch.setattr(seed_cli, "_resolve_target_module", lambda target, schema: module_path)
    monkeypatch.setattr(seed_cli, "_create_plan", lambda **kwargs: "plan")
    monkeypatch.setattr(
        seed_cli,
        "_create_beanie_client",
        lambda database: SimpleNamespace(close=lambda: None),
    )

    class DummyBeanieSeeder:
        def __init__(
            self,
            plan: object,
            client_factory: callable,
            *,
            database_name: str,
            logger: object,
        ) -> None:
            recorded["database_name"] = database_name
            recorded["client"] = client_factory()

        def seed(
            self,
            *,
            count: int,
            batch_size: int,
            cleanup: bool,
            dry_run: bool,
        ) -> SimpleNamespace:
            recorded["seed_args"] = {
                "count": count,
                "batch_size": batch_size,
                "cleanup": cleanup,
                "dry_run": dry_run,
            }
            return SimpleNamespace(inserted=count, cleanup=cleanup, dry_run=dry_run)

    monkeypatch.setattr("pydantic_fixturegen.orm.beanie.BeanieSeeder", DummyBeanieSeeder)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "beanie",
            str(module_path),
            "--database",
            "mongodb://localhost/appdb",
            "--cleanup",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert recorded["database_name"] == "appdb"
    assert recorded["seed_args"]["cleanup"] is True


def test_seed_sqlmodel_reports_discovery_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = create_cli_runner()
    errors = _suppress_seed_cli_exit(monkeypatch)

    def fail_resolve(target: str | None, schema: Path | None) -> Path:
        raise DiscoveryError("missing target")

    monkeypatch.setattr(seed_cli, "_resolve_target_module", fail_resolve)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "sqlmodel",
            str(tmp_path / "missing.py"),
            "--database",
            "sqlite:///tmp.db",
        ],
    )

    assert result.exit_code == 0
    assert errors and "missing target" in str(errors[0])


def test_seed_sqlmodel_reports_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = create_cli_runner()
    errors = _suppress_seed_cli_exit(monkeypatch)
    module_path = tmp_path / "models.py"
    module_path.write_text("pass", encoding="utf-8")

    monkeypatch.setattr(seed_cli, "_resolve_target_module", lambda target, schema: module_path)

    def fail_plan(**kwargs: object) -> object:
        raise ConfigError("bad config")

    monkeypatch.setattr(seed_cli, "_create_plan", fail_plan)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "sqlmodel",
            str(module_path),
            "--database",
            "sqlite:///tmp.db",
        ],
    )

    assert result.exit_code == 0
    assert errors and "bad config" in str(errors[0])


def test_seed_beanie_reports_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = create_cli_runner()
    errors = _suppress_seed_cli_exit(monkeypatch)
    module_path = tmp_path / "models.py"
    module_path.write_text("pass", encoding="utf-8")
    monkeypatch.setattr(seed_cli, "_resolve_target_module", lambda target, schema: module_path)
    monkeypatch.setattr(
        seed_cli,
        "_create_plan",
        lambda **kwargs: (_ for _ in ()).throw(ConfigError("invalid plan")),
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "seed",
            "beanie",
            str(module_path),
            "--database",
            "mongodb://localhost/appdb",
        ],
    )

    assert result.exit_code == 0
    assert errors and "invalid plan" in str(errors[0])
