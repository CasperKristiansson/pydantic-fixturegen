from __future__ import annotations

import datetime
import json
import textwrap
from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot, JsonGenerationResult
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import json as json_mod
from pydantic_fixturegen.core.config import ConfigError
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, MappingError
from pydantic_fixturegen.core.path_template import OutputTemplate
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


def test_gen_json_out_template(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "artifacts" / "{model}" / "sample-{case_index}"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(template),
            "--include",
            "models.User",
            "--n",
            "3",
            "--shard-size",
            "1",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    emitted = sorted((tmp_path / "artifacts" / "User").glob("sample-*.json"))
    assert [path.name for path in emitted] == ["sample-1.json", "sample-2.json", "sample-3.json"]
    stdout_text = result.stdout
    for path in emitted:
        assert str(path) in stdout_text


def test_gen_json_out_template_invalid_field(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "{unknown}.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(template),
            "--include",
            "models.User",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported template variable" in result.stdout or result.stderr


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
    assert text.endswith("\n")
    assert "\n" not in text[:-1]


def test_gen_json_now_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "anchored.json"

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(output,),
            base_output=output,
            model=None,
            config=ConfigSnapshot(
                seed=None,
                include=(),
                exclude=(),
                time_anchor=datetime.datetime(2024, 12, 1, 8, 9, 10, tzinfo=datetime.timezone.utc),
            ),
            constraint_summary=None,
            warnings=(),
            delegated=False,
        )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        fake_generate,
    )

    now_value = "2024-12-01T08:09:10Z"

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
            "--now",
            now_value,
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert captured["now"] == now_value


def test_gen_json_mapping_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"
    summary = {
        "models": [
            {
                "model": "models.User",
                "attempts": 1,
                "successes": 0,
                "fields": [
                    {
                        "name": "value",
                        "constraints": None,
                        "attempts": 1,
                        "successes": 0,
                        "failures": [
                            {
                                "location": ["value"],
                                "message": "failed",
                                "error_type": "value_error",
                                "value": None,
                                "hint": "check constraints",
                            }
                        ],
                    }
                ],
            }
        ],
        "total_models": 1,
        "models_with_failures": 1,
        "total_failures": 1,
    }

    error = MappingError(
        "Failed to generate instance for models.User.",
        details={
            "constraint_summary": summary,
            "config": {
                "seed": None,
                "include": ["models.User"],
                "exclude": [],
                "time_anchor": None,
            },
            "warnings": ["warn"],
            "base_output": str(output),
        },
    )

    def raise_error(**_: object):  # noqa: ANN001
        raise error

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_error,
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
    assert "Constraint violations detected." in result.stderr
    assert "Constraint report" in result.stdout
    assert "hint:" in result.stdout


def test_gen_json_emit_artifact_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    delegated = JsonGenerationResult(
        paths=(),
        base_output=output,
        model=None,
        config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        constraint_summary=None,
        warnings=(),
        delegated=True,
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        lambda **_: delegated,
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

    assert result.exit_code == 0
    assert not output.exists()


def test_gen_json_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    error = EmitError(
        "boom",
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

    def raise_error(**_: object):  # noqa: ANN001
        raise error

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_error,
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

    assert result.exit_code == 30
    assert "boom" in result.stderr


def test_execute_json_command_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_path = tmp_path / "emitted.json"
    result = JsonGenerationResult(
        paths=(out_path,),
        base_output=out_path,
        model=None,
        config=ConfigSnapshot(seed=42, include=("pkg.User",), exclude=(), time_anchor=None),
        constraint_summary=None,
        warnings=("warn",),
        delegated=False,
    )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        lambda **_: result,
    )

    json_mod._execute_json_command(
        target="module",
        output_template=OutputTemplate(str(out_path)),
        count=1,
        jsonl=False,
        indent=0,
        use_orjson=True,
        shard_size=None,
        include="pkg.User",
        exclude=None,
        seed=42,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
    )

    captured = capsys.readouterr()
    assert "warn" in captured.err
    assert str(out_path) in captured.out


def test_execute_json_command_discovery_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    err = DiscoveryError("fail")

    def raise_discovery(**_: object):  # noqa: ANN001
        raise err

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_discovery,
    )

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target="module",
            output_template=OutputTemplate(str(tmp_path / "result.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_gen_json_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    def raise_config(**_: Any) -> JsonGenerationResult:
        raise ConfigError("bad config")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_config,
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
    assert "bad config" in result.stderr


def test_execute_json_command_emit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    error = EmitError(
        "broken",
        details={
            "config": {
                "seed": None,
                "include": [],
                "exclude": [],
                "time_anchor": None,
            },
            "warnings": [],
            "base_output": str(tmp_path / "result.json"),
        },
    )

    def raise_error(**_: object):  # noqa: ANN001
        raise error

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_error,
    )

    with pytest.raises(EmitError):
        json_mod._execute_json_command(
            target="module",
            output_template=OutputTemplate(str(tmp_path / "result.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_execute_json_command_path_checks(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    missing = module_path.with_name("missing.py")

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target=str(missing),
            output_template=OutputTemplate(str(module_path)),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )

    as_dir = tmp_path / "dir"
    as_dir.mkdir()

    with pytest.raises(DiscoveryError):
        json_mod._execute_json_command(
            target=str(as_dir),
            output_template=OutputTemplate(str(module_path)),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_execute_json_command_applies_preset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_path = tmp_path / "sample.json"
    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(out_path,),
            base_output=out_path,
            model=None,
            config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
            constraint_summary=None,
            warnings=(),
            delegated=False,
        )

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        fake_generate,
    )

    json_mod._execute_json_command(
        target="module",
        output_template=OutputTemplate(str(out_path)),
        count=1,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
        include=None,
        exclude=None,
        seed=None,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset="boundary",
    )

    assert captured["preset"] == "boundary"


def test_gen_json_load_model_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "out.json"

    def raise_discovery(**_: Any) -> JsonGenerationResult:
        raise DiscoveryError("boom")

    monkeypatch.setattr(
        "pydantic_fixturegen.cli.gen.json.generate_json_artifacts",
        raise_discovery,
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


def test_gen_json_handles_relative_imports(tmp_path: Path) -> None:
    target_module = _write_relative_import_package(tmp_path)
    output = tmp_path / "request.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(target_module),
            "--out",
            str(output),
            "--include",
            "lib.models.example_model.ExampleRequest",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert output.exists()
