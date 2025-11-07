from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.api.models import ConfigSnapshot, SchemaGenerationResult
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import schema as schema_mod
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, WatchError
from pydantic_fixturegen.core.path_template import OutputTemplate
from tests._cli import create_cli_runner

runner = create_cli_runner()


class FakeLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.warn_calls: list[tuple[str, dict[str, object]]] = []

    def debug(self, message: str, **kwargs: object) -> None:  # noqa: D401
        self.debug_calls.append((message, kwargs))

    def info(self, message: str, **kwargs: object) -> None:
        self.info_calls.append((message, kwargs))

    def warn(self, message: str, **kwargs: object) -> None:
        self.warn_calls.append((message, kwargs))


class DummyModel(BaseModel):
    value: int


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Address(BaseModel):
    city: str
    zip_code: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class Product(BaseModel):
    sku: str
    price: float
""",
        encoding="utf-8",
    )
    return module_path


def _write_relative_import_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "lib" / "models"
    package_root.mkdir(parents=True)

    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "__init__.py").write_text("", encoding="utf-8")

    (package_root / "shared_model.py").write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel


            class SharedPayload(BaseModel):
                path: str
                size: int
            """
        ),
        encoding="utf-8",
    )

    target_module = package_root / "example_model.py"
    target_module.write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel

            from .shared_model import SharedPayload


            class ExampleRequest(BaseModel):
                project_id: str
                payload: SharedPayload
            """
        ),
        encoding="utf-8",
    )

    return target_module


def test_gen_schema_single_model(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "user_schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["title"] == "User"
    assert "properties" in payload


def test_gen_schema_combined_models(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "bundle.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"Address", "Product", "User"}


def test_gen_schema_indent_override(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "compact.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.Address",
            "--indent",
            "0",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "\n" not in text[:-1]


def test_gen_schema_out_template(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "schemas" / "{model}" / "schema-{timestamp}.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(template),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    emitted = list((tmp_path / "schemas" / "User").glob("schema-*.json"))
    assert len(emitted) == 1
    payload = json.loads(emitted[0].read_text(encoding="utf-8"))
    assert payload["title"] == "User"


def test_gen_schema_invalid_template_reports_error(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "{unknown}" / "schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(template),
        ],
    )

    assert result.exit_code == 30
    assert "Unsupported template variable" in result.stderr


def test_gen_schema_template_model_requires_single_selection(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "{model}" / "bundle.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(template),
        ],
    )

    assert result.exit_code == 30
    assert "requires a single model" in result.stderr


def test_gen_schema_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    output = tmp_path / "schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(missing),
            "--out",
            str(output),
            "--json-errors",
        ],
    )

    assert result.exit_code == 10
    assert "Target path" in result.stdout


def test_gen_schema_emit_artifact_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    delegated = SchemaGenerationResult(
        path=None,
        base_output=output,
        models=(),
        config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        warnings=(),
        delegated=True,
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        lambda **_: delegated,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0
    assert not output.exists()


def test_gen_schema_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"
    error = EmitError(
        "bad",
        details={
            "config": {
                "seed": None,
                "include": [],
                "exclude": [],
                "time_anchor": None,
            },
            "warnings": [],
            "base_output": str(output),
        },
    )

    def raise_error(**_: dict[str, object]) -> SchemaGenerationResult:
        raise error

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        raise_error,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 30
    assert "bad" in result.stderr


def test_gen_schema_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    def raise_config(**_: object) -> SchemaGenerationResult:  # noqa: ANN003
        raise ConfigError("broken")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        raise_config,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 10
    assert "broken" in result.stderr


def test_execute_schema_command_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SchemaGenerationResult(
        path=tmp_path / "schema.json",
        base_output=tmp_path / "schema.json",
        models=(),
        config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        warnings=("warn",),
        delegated=False,
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        lambda **_: result,
    )

    schema_mod._execute_schema_command(
        target="module",
        output_template=OutputTemplate(str(tmp_path / "schema.json")),
        indent=None,
        include=None,
        exclude=None,
    )

    captured = capsys.readouterr()
    assert "warn" in captured.err


def test_execute_schema_command_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_discovery(**_: object) -> SchemaGenerationResult:
        raise DiscoveryError("boom")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        raise_discovery,
    )

    with pytest.raises(DiscoveryError):
        schema_mod._execute_schema_command(
            target="module",
            output_template=OutputTemplate(str(tmp_path / "schema.json")),
            indent=None,
            include=None,
            exclude=None,
        )


def test_execute_schema_command_load_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_discovery(**_: object) -> SchemaGenerationResult:
        raise DiscoveryError("boom")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.schema.generate_schema_artifacts",
        raise_discovery,
    )

    with pytest.raises(DiscoveryError):
        schema_mod._execute_schema_command(
            target="module",
            output_template=OutputTemplate(str(tmp_path / "schema.json")),
            indent=None,
            include=None,
            exclude=None,
        )


def test_gen_schema_handles_relative_imports(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)
    output = tmp_path / "schema.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(target_module),
            "--out",
            str(output),
            "--include",
            "lib.models.example_model.ExampleRequest",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload.get("title") == "ExampleRequest"


def test_log_schema_snapshot_records_events(tmp_path: Path) -> None:
    logger = FakeLogger()
    time_anchor = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    result = SchemaGenerationResult(
        path=tmp_path / "schema.json",
        base_output=tmp_path,
        models=(DummyModel,),
        config=ConfigSnapshot(
            seed=None,
            include=("A",),
            exclude=(),
            time_anchor=time_anchor,
        ),
        warnings=("warn1",),
        delegated=False,
    )

    delegated = schema_mod._log_schema_snapshot(logger, result)

    assert delegated is False
    assert logger.debug_calls[0][0] == "Loaded configuration"
    assert any(info[1].get("event") == "schema_generation_complete" for info in logger.info_calls)
    assert logger.info_calls[0][1]["event"] == "temporal_anchor_set"
    assert logger.warn_calls and logger.warn_calls[0][0] == "warn1"


def test_log_schema_snapshot_delegated(tmp_path: Path) -> None:
    logger = FakeLogger()
    result = SchemaGenerationResult(
        path=None,
        base_output=tmp_path,
        models=(DummyModel,),
        config=ConfigSnapshot(
            seed=None,
            include=(),
            exclude=(),
            time_anchor=None,
        ),
        warnings=(),
        delegated=True,
    )

    delegated = schema_mod._log_schema_snapshot(logger, result)

    assert delegated is True
    assert any(info[1].get("event") == "schema_generation_delegated" for info in logger.info_calls)


def test_handle_schema_error_logs_config() -> None:
    logger = FakeLogger()
    error = EmitError(
        "bad",
        details={
            "config": {
                "include": ["A"],
                "exclude": [],
                "time_anchor": "2024-01-01T00:00:00+00:00",
            },
            "warnings": ["warnA", "warnB"],
        },
    )

    schema_mod._handle_schema_error(logger, error)

    assert logger.debug_calls and logger.debug_calls[0][1]["event"] == "config_loaded"
    assert any(info[1].get("event") == "temporal_anchor_set" for info in logger.info_calls)
    assert [call[0] for call in logger.warn_calls] == ["warnA", "warnB"]


def test_gen_schema_watch_mode_handles_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"
    logger = FakeLogger()
    monkeypatch.setattr(schema_mod, "get_logger", lambda: logger)

    invoked: dict[str, int] = {"count": 0}

    def fake_execute(**_: object) -> None:  # noqa: ANN001
        invoked["count"] += 1

    monkeypatch.setattr(schema_mod, "_execute_schema_command", fake_execute)
    monkeypatch.setattr(
        schema_mod,
        "gather_default_watch_paths",
        lambda *args, **kwargs: [tmp_path],  # noqa: ARG005
    )

    def fake_run_with_watch(callback: object, watch_paths: list[Path], debounce: float) -> None:
        assert watch_paths == [tmp_path]
        assert debounce == 0.5
        callback()
        raise WatchError("watch failed")

    monkeypatch.setattr(schema_mod, "run_with_watch", fake_run_with_watch)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "schema",
            str(module_path),
            "--out",
            str(output),
            "--watch",
        ],
    )

    assert result.exit_code == 60
    assert invoked["count"] == 1
    assert logger.debug_calls and logger.debug_calls[0][0] == "Entering watch loop"
