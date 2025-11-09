from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot, DatasetGenerationResult
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import dataset as dataset_module
from pydantic_fixturegen.cli.gen.dataset import _execute_dataset_command
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.logging import get_logger
from tests._cli import create_cli_runner


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "dataset_models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int
    email: str
""",
        encoding="utf-8",
    )
    return module_path


def _suppress_dataset_cli_exit(monkeypatch) -> list[Exception]:
    original_render = dataset_module.render_cli_error
    captured: list[Exception] = []

    def patched(error: Exception, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original_render(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(dataset_module, "render_cli_error", patched)
    return captured


def test_gen_dataset_writes_csv(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_path = tmp_path / "users.csv"
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(out_path),
            "--format",
            "csv",
            "--n",
            "3",
            "--include",
            "dataset_models.User",
            "--seed",
            "123",
            "--max-depth",
            "2",
            "--on-cycle",
            "reuse",
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic aid
        print(result.stdout)
    assert result.exit_code == 0
    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("id,email,__cycles__")
    assert len(lines) == 4  # header + 3 records


def test_gen_dataset_handles_sharded_output(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_template = tmp_path / "sharded-{case_index}.csv"
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(out_template),
            "--format",
            "csv",
            "--n",
            "5",
            "--shard-size",
            "2",
            "--include",
            "dataset_models.User",
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic aid
        print(result.stdout)
    assert result.exit_code == 0
    shards = sorted(out_template.parent.glob("sharded-*.csv"))
    assert len(shards) == 3
    total_lines = sum(len(s.read_text(encoding="utf-8").strip().splitlines()) - 1 for s in shards)
    assert total_lines == 5


def test_gen_dataset_requires_target_or_schema(monkeypatch, tmp_path: Path) -> None:
    errors = _suppress_dataset_cli_exit(monkeypatch)
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            "--out",
            str(tmp_path / "noop.csv"),
        ],
    )
    assert result.exit_code == 0
    assert any("Provide a module path" in str(err) for err in errors)


def test_gen_dataset_conflicting_schema_and_target(monkeypatch, tmp_path: Path) -> None:
    errors = _suppress_dataset_cli_exit(monkeypatch)
    module_path = _write_module(tmp_path)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--schema",
            str(schema_path),
            "--out",
            str(tmp_path / "out.csv"),
        ],
    )
    assert result.exit_code == 0
    assert any("either a module path or --schema" in str(err) for err in errors)


def test_gen_dataset_reports_missing_schema(monkeypatch, tmp_path: Path) -> None:
    errors = _suppress_dataset_cli_exit(monkeypatch)
    schema_path = tmp_path / "missing.json"
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            "--schema",
            str(schema_path),
            "--out",
            str(tmp_path / "out.csv"),
        ],
    )
    assert result.exit_code == 0
    assert any("does not exist" in str(err) for err in errors)


def test_gen_dataset_schema_ingest_failure(monkeypatch, tmp_path: Path) -> None:
    errors = _suppress_dataset_cli_exit(monkeypatch)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")

    def raise_ingest_error(self, _: Path) -> None:
        raise DiscoveryError("invalid schema")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.SchemaIngester.ingest_json_schema",
        raise_ingest_error,
    )

    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            "--schema",
            str(schema_path),
            "--out",
            str(tmp_path / "schema.csv"),
        ],
    )
    assert result.exit_code == 0
    assert any("invalid schema" in str(err) for err in errors)


def test_gen_dataset_schema_ingest(monkeypatch, tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")

    class DummyIngestion:
        def __init__(self, path: Path) -> None:
            self.path = path

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.SchemaIngester.ingest_json_schema",
        lambda self, _: DummyIngestion(module_path),
    )

    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            "--schema",
            str(schema_path),
            "--out",
            str(tmp_path / "schema.csv"),
            "--include",
            "dataset_models.User",
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic aid
        print(result.stdout)
    assert result.exit_code == 0


def test_gen_dataset_wraps_config_errors(monkeypatch, tmp_path: Path) -> None:
    errors = _suppress_dataset_cli_exit(monkeypatch)
    module_path = _write_module(tmp_path)

    def raise_config_error(**_: object) -> None:
        raise ConfigError("broken config")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset._execute_dataset_command",
        raise_config_error,
    )

    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(tmp_path / "out.csv"),
            "--include",
            "dataset_models.User",
        ],
    )
    assert result.exit_code == 0
    assert any("broken config" in str(err) for err in errors)


def test_gen_dataset_watch_requires_module(monkeypatch, tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.SchemaIngester.ingest_json_schema",
        lambda self, _: type("Ingestion", (), {"path": schema_path}),
    )
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            "--schema",
            str(schema_path),
            "--out",
            str(tmp_path / "out.csv"),
            "--watch",
        ],
    )
    assert result.exit_code != 0


def test_gen_dataset_watch_handles_dynamic_directories(monkeypatch, tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_path = tmp_path / "{model}" / "data.csv"

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset._execute_dataset_command",
        lambda **_: None,
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.gather_default_watch_paths",
        lambda module_path, output, extra: ["module.py"],
    )

    run_calls: dict[str, object] = {}

    def fake_watch(callback, paths, debounce):
        run_calls["paths"] = paths
        run_calls["debounce"] = debounce
        callback()

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.run_with_watch",
        fake_watch,
    )

    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "dataset",
            str(module_path),
            "--out",
            str(out_path),
            "--watch",
            "--include",
            "dataset_models.User",
        ],
    )

    assert result.exit_code == 0
    assert run_calls.get("paths") == ["module.py"]


def test_execute_dataset_command_handles_generation_error(monkeypatch, tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    def boom(**_: object) -> None:
        raise DiscoveryError("boom", details={"config": {"seed": 1}})

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.generate_dataset_artifacts",
        boom,
    )
    template = OutputTemplate(str(tmp_path / "err.csv"))
    with pytest.raises(DiscoveryError):
        _execute_dataset_command(
            target=str(module_path),
            output_template=template,
            count=1,
            dataset_format="csv",
            compression=None,
            shard_size=None,
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
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            logger=get_logger(),
        )


def test_execute_dataset_command_handles_delegated(monkeypatch, tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = OutputTemplate(str(tmp_path / "delegated.csv"))
    destination = tmp_path / "delegated.csv"
    destination.write_text("header\n", encoding="utf-8")
    snapshot = ConfigSnapshot(
        seed=123,
        include=("dataset_models.User",),
        exclude=(),
        time_anchor=None,
    )
    result = DatasetGenerationResult(
        paths=(destination,),
        base_output=destination,
        model=type("User", (), {}),
        config=snapshot,
        warnings=(),
        constraint_summary=None,
        delegated=True,
        format="csv",
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.dataset.generate_dataset_artifacts",
        lambda **_: result,
    )
    _execute_dataset_command(
        target=str(module_path),
        output_template=template,
        count=1,
        dataset_format="csv",
        compression=None,
        shard_size=None,
        include=None,
        exclude=None,
        seed=123,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        profile=None,
        respect_validators=None,
        validator_max_retries=None,
        links=None,
        max_depth=None,
        cycle_policy=None,
        rng_mode=None,
        logger=get_logger(),
    )


def test_execute_dataset_command_requires_target(tmp_path: Path) -> None:
    template = OutputTemplate(str(tmp_path / "missing.csv"))
    with pytest.raises(DiscoveryError):
        _execute_dataset_command(
            target=None,
            output_template=template,
            count=1,
            dataset_format="csv",
            compression=None,
            shard_size=None,
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
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            logger=get_logger(),
        )


def test_log_dataset_generation_snapshot_handles_anchor_and_warnings(tmp_path: Path) -> None:
    destination = tmp_path / "data.csv"
    destination.write_text("", encoding="utf-8")
    snapshot = ConfigSnapshot(
        seed=7,
        include=("dataset_models.User",),
        exclude=("tests.*",),
        time_anchor=dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc),
    )
    result = DatasetGenerationResult(
        paths=(destination,),
        base_output=destination,
        model=type("User", (), {}),
        config=snapshot,
        warnings=("caution",),
        constraint_summary=None,
        delegated=False,
        format="csv",
    )
    assert (
        dataset_module._log_dataset_generation_snapshot(
            get_logger(),
            result,
            count=3,
        )
        is False
    )


def test_handle_generation_error_logs_time_anchor() -> None:
    error = DiscoveryError(
        "boom",
        details={
            "config": {
                "seed": 9,
                "include": ["dataset_models.User"],
                "exclude": [],
                "time_anchor": "2024-01-05T00:00:00+00:00",
            }
        },
    )

    dataset_module._handle_generation_error(get_logger(), error)
