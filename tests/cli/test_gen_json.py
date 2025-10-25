from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import json as json_mod
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from typer.testing import CliRunner

runner = CliRunner()


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
""",
        encoding="utf-8",
    )
    return module_path


def test_gen_json_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "users.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--n",
            "2",
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    assert "address" in data[0]


def test_gen_json_jsonl_shards(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "samples.jsonl"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--jsonl",
            "--shard-size",
            "2",
            "--n",
            "5",
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    shard_paths = sorted(tmp_path.glob("samples-*.jsonl"))
    assert len(shard_paths) == 3
    line_counts = [len(path.read_text(encoding="utf-8").splitlines()) for path in shard_paths]
    assert line_counts == [2, 2, 1]


def test_gen_json_respects_config_env(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "compact.json"

    env = {"PFG_JSON__INDENT": "0"}
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
        env=env,
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert "\n" not in text


def test_gen_json_mapping_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    class DummyGenerator:
        def generate_one(self, model):  # noqa: ANN001
            return None

    def dummy_builder(_: object) -> DummyGenerator:
        return DummyGenerator()

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json._build_instance_generator",
        dummy_builder,
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 20
    assert "Failed to generate instance" in result.stderr


def test_gen_json_emit_artifact_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.emit_artifact",
        lambda *args, **kwargs: True,
    )

    def fail_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("emit_json_samples should not be called")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.json.emit_json_samples", fail_emit)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 0
    assert not output.exists()


def test_gen_json_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    def boom_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        raise RuntimeError("boom")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.json.emit_json_samples", boom_emit)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 30
    assert "boom" in result.stderr


def test_execute_json_command_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module_path = _write_module(tmp_path)
    info = IntrospectedModel(
        module="pkg",
        name="User",
        qualname="pkg.User",
        locator=str(module_path),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    class DemoModel(BaseModel):
        id: int

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(models=[info], warnings=["warn"], errors=[])

    class DummyGenerator:
        def generate_one(self, model):  # noqa: ANN001
            return DemoModel(id=1)

    monkeypatch.setattr(json_mod, "discover_models", fake_discover)
    monkeypatch.setattr(json_mod, "load_model_class", lambda _: DemoModel)
    monkeypatch.setattr(json_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(json_mod, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(json_mod, "_build_instance_generator", lambda _: DummyGenerator())

    out_path = tmp_path / "emitted.json"

    def fake_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        return [out_path]

    monkeypatch.setattr(json_mod, "emit_json_samples", fake_emit)
    monkeypatch.setattr(json_mod, "emit_artifact", lambda *a, **k: False)

    json_mod._execute_json_command(
        target=str(module_path),
        out=out_path,
        count=1,
        jsonl=False,
        indent=0,
        use_orjson=True,
        shard_size=None,
        include="pkg.User",
        exclude=None,
        seed=42,
    )

    captured = capsys.readouterr()
    assert "warn" in captured.out
    assert str(out_path) in captured.out


def test_execute_json_command_discovery_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(models=[], warnings=[], errors=["fail"])

    monkeypatch.setattr(json_mod, "discover_models", fake_discover)
    monkeypatch.setattr(json_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(json_mod, "load_entrypoint_plugins", lambda: None)

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target=str(module_path),
            out=module_path,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
        )


def test_gen_json_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    def bad_config(**_: object):  # noqa: ANN003
        raise ConfigError("bad config")

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.json.load_config", bad_config)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 10
    assert "bad config" in result.stderr


def test_execute_json_command_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    info = IntrospectedModel(
        module="pkg",
        name="User",
        qualname="pkg.User",
        locator=str(module_path),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    class DemoModel(BaseModel):
        id: int

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module_path
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    class DummyGenerator:
        def generate_one(self, model):  # noqa: ANN001
            return DemoModel(id=1)

    monkeypatch.setattr(json_mod, "discover_models", fake_discover)
    monkeypatch.setattr(json_mod, "load_model_class", lambda _: DemoModel)
    monkeypatch.setattr(json_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(json_mod, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(json_mod, "_build_instance_generator", lambda _: DummyGenerator())
    monkeypatch.setattr(json_mod, "emit_artifact", lambda *a, **k: False)

    def boom_emit(*args, **kwargs):  # noqa: ANN001, ANN002
        raise RuntimeError("broken")

    monkeypatch.setattr(json_mod, "emit_json_samples", boom_emit)

    with pytest.raises(EmitError):
        json_mod._execute_json_command(
            target=str(module_path),
            out=module_path,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
        )


def test_execute_json_command_path_checks(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing = module_path.with_name("missing.py")

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target=str(missing),
            out=module_path,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
        )

    as_dir = tmp_path / "dir"
    as_dir.mkdir()

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target=str(as_dir),
            out=module_path,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
        )


def test_gen_json_load_model_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.load_model_class",
        lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code == 10
    assert "boom" in result.stderr
