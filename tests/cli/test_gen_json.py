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
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, MappingError, WatchError
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.polyfactory_support.discovery import (
    POLYFACTORY_MODEL_FACTORY,
    POLYFACTORY_UNAVAILABLE_REASON,
)
from tests._cli import create_cli_runner

try:  # pragma: no cover
    import polyfactory  # noqa: F401
except Exception:  # pragma: no cover
    polyfactory = None

runner = create_cli_runner()


class FakeLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.warn_calls: list[tuple[str, dict[str, object]]] = []
        self.config = type("Config", (), {"json": False})()

    def debug(self, message: str, **kwargs: object) -> None:
        self.debug_calls.append((message, kwargs))

    def info(self, message: str, **kwargs: object) -> None:
        self.info_calls.append((message, kwargs))

    def warn(self, message: str, **kwargs: object) -> None:
        self.warn_calls.append((message, kwargs))


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


def _write_linked_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "linked_models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str


class Order(BaseModel):
    order_id: int
    user_id: int | None = None
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


def test_gen_json_prefers_polyfactory_factories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if polyfactory is None:
        pytest.skip("polyfactory unavailable")
    if POLYFACTORY_MODEL_FACTORY is None:
        pytest.skip(POLYFACTORY_UNAVAILABLE_REASON or "polyfactory unavailable")
    monkeypatch.setenv("PFG_POLYFACTORY__ENABLED", "true")
    monkeypatch.setenv("PFG_POLYFACTORY__PREFER_DELEGATION", "true")
    module_path = tmp_path / "models.py"
    module_path.write_text(
        textwrap.dedent(
            """
            from pydantic import BaseModel
            from polyfactory.factories.pydantic_factory import ModelFactory


            class User(BaseModel):
                name: str = "fixturegen"


            class UserFactory(ModelFactory[User]):
                __model__ = User
                __check_model__ = False

                @classmethod
                def build(cls, factory_use_construct: bool = False, **kwargs):  # noqa: ARG002
                    return User(name="delegated")
            """
        ),
        encoding="utf-8",
    )

    output = tmp_path / "delegated.json"
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
            "--n",
            "1",
        ],
        env={
            "PFG_POLYFACTORY__ENABLED": "true",
            "PFG_POLYFACTORY__PREFER_DELEGATION": "true",
        },
    )
    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["name"] == "delegated"


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


def test_gen_json_supports_dataclass_and_typeddict(tmp_path: Path) -> None:
    module_path = tmp_path / "mixed_models.py"
    module_path.write_text(
        textwrap.dedent(
            """
            from dataclasses import dataclass
            from typing import TypedDict


            class AuditInfo(TypedDict):
                level: str
                actor: str


            @dataclass
            class Event:
                name: str
                audit: AuditInfo
            """
        ),
        encoding="utf-8",
    )
    output = tmp_path / "events.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "mixed_models.Event",
            "--n",
            "1",
        ],
    )

    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    events = json.loads(output.read_text(encoding="utf-8"))
    assert events[0]["audit"].keys() >= {"level", "actor"}


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


def test_gen_json_type_expression(tmp_path: Path) -> None:
    output = tmp_path / "values.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--type",
            "list[int]",
            "--out",
            str(output),
            "--n",
            "3",
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 3
    for entry in payload:
        assert isinstance(entry, list)
        assert all(isinstance(item, int) for item in entry)


def test_gen_json_type_expression_with_module_context(tmp_path: Path) -> None:
    module_path = tmp_path / "shapes.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Payload(BaseModel):
    value: int
    name: str
""",
        encoding="utf-8",
    )
    output = tmp_path / "payload.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--type",
            "list[Payload]",
            "--out",
            str(output),
            "--n",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert isinstance(payload[0], list)
    assert all(set(item.keys()) == {"value", "name"} for item in payload[0])


def test_gen_json_type_expression_invalid_name(tmp_path: Path) -> None:
    output = tmp_path / "values.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--type",
            "list[MissingModel]",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "Unknown name in type expression" in combined


def test_gen_json_type_expression_watch_requires_module(tmp_path: Path) -> None:
    output = tmp_path / "values.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--type",
            "list[int]",
            "--out",
            str(output),
            "--watch",
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "requires a module path" in combined


def test_gen_json_type_expression_disallows_links(tmp_path: Path) -> None:
    output = tmp_path / "values.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--type",
            "list[int]",
            "--out",
            str(output),
            "--link",
            "User.id=Order.user_id",
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "--link is not supported when using --type" in combined


def test_gen_json_type_expression_disallows_with_related(tmp_path: Path) -> None:
    output = tmp_path / "values.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--type",
            "list[int]",
            "--out",
            str(output),
            "--with-related",
            "User",
        ],
    )

    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "--with-related is not supported when using --type" in combined


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


def test_gen_json_validator_flags_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "validators.json"

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(output,),
            base_output=output,
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

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--respect-validators",
            "--validator-max-retries",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert captured["respect_validators"] is True


def test_gen_json_field_hints_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "field-hints.json"

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(output,),
            base_output=output,
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

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--field-hints",
            "examples",
        ],
    )

    assert result.exit_code == 0
    assert captured["field_hints"] == "examples"


def test_gen_json_collection_flags_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "collection-flags.json"

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> JsonGenerationResult:
        captured.update(kwargs)
        return JsonGenerationResult(
            paths=(output,),
            base_output=output,
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

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--collection-min-items",
            "2",
            "--collection-max-items",
            "4",
            "--collection-distribution",
            "max-heavy",
        ],
    )

    assert result.exit_code == 0
    assert captured["collection_min_items"] == 2
    assert captured["collection_max_items"] == 4
    assert captured["collection_distribution"] == "max-heavy"


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


def test_gen_json_with_related_bundle(tmp_path: Path) -> None:
    module_path = _write_linked_module(tmp_path)
    output = tmp_path / "bundle.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--include",
            "linked_models.Order",
            "--with-related",
            "User",
            "--link",
            "linked_models.Order.user_id=linked_models.User.id",
            "--n",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload
    record = payload[0]
    assert set(record.keys()) == {"Order", "User"}
    assert record["Order"]["user_id"] == record["User"]["id"]


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


def test_gen_json_watch_mode_handles_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_relative_import_package(tmp_path)
    output = tmp_path / "samples.json"
    logger = FakeLogger()
    monkeypatch.setattr(json_mod, "get_logger", lambda: logger)

    invoked: dict[str, int] = {"count": 0}

    def fake_execute(**_: object) -> None:  # noqa: ANN001
        invoked["count"] += 1

    monkeypatch.setattr(json_mod, "_execute_json_command", fake_execute)
    monkeypatch.setattr(
        json_mod,
        "gather_default_watch_paths",
        lambda *args, **kwargs: [tmp_path],  # noqa: ARG005
    )

    def fake_run_with_watch(callback: object, watch_paths: list[Path], debounce: float) -> None:
        assert watch_paths == [tmp_path]
        assert debounce == 0.5
        callback()
        raise WatchError("watch failed")

    monkeypatch.setattr(json_mod, "run_with_watch", fake_run_with_watch)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module_path),
            "--out",
            str(output),
            "--watch",
        ],
    )

    assert result.exit_code == 60
    assert invoked["count"] == 1
    assert logger.debug_calls and logger.debug_calls[0][0] == "Entering watch loop"


def test_log_generation_snapshot_records_paths(tmp_path: Path) -> None:
    logger = FakeLogger()
    result = JsonGenerationResult(
        paths=(tmp_path / "data.json",),
        base_output=tmp_path,
        model=None,
        config=ConfigSnapshot(
            seed=123,
            include=("A",),
            exclude=(),
            time_anchor=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        ),
        constraint_summary={"fields": 1},
        warnings=("warn",),
        delegated=False,
    )

    delegated = json_mod._log_generation_snapshot(logger, result, count=2)

    assert delegated is False
    assert logger.debug_calls and logger.debug_calls[0][1]["event"] == "config_loaded"
    assert any(info[1].get("event") == "json_generation_complete" for info in logger.info_calls)
    assert logger.warn_calls[0][0] == "warn"


def test_log_generation_snapshot_delegated(tmp_path: Path) -> None:
    logger = FakeLogger()
    result = JsonGenerationResult(
        paths=(),
        base_output=tmp_path,
        model=None,
        config=ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None),
        constraint_summary=None,
        warnings=(),
        delegated=True,
    )

    delegated = json_mod._log_generation_snapshot(logger, result, count=1)

    assert delegated is True
    assert any(info[1].get("event") == "json_generation_delegated" for info in logger.info_calls)


def test_handle_generation_error_logs_details(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = FakeLogger()
    captured: list[dict[str, Any]] = []

    monkeypatch.setattr(
        json_mod,
        "emit_constraint_summary",
        lambda summary, logger, json_mode: captured.append(summary),  # noqa: ARG005
    )

    error = EmitError(
        "bad",
        details={
            "config": {
                "seed": 1,
                "include": ["A"],
                "exclude": [],
                "time_anchor": "2024-01-01T00:00:00+00:00",
            },
            "warnings": ["warn1"],
            "constraint_summary": {"fields": 3},
        },
    )

    json_mod._handle_generation_error(logger, error)

    assert logger.debug_calls and logger.debug_calls[0][1]["event"] == "config_loaded"
    assert logger.warn_calls[0][0] == "warn1"
    assert captured == [{"fields": 3}]


def test_gen_json_from_schema(tmp_path: Path) -> None:
    schema_path = tmp_path / "user.schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "title": "User",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string"},
                },
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "user.json"
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            "--schema",
            str(schema_path),
            "--out",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload, "expected at least one emitted sample"
    assert set(payload[0].keys()) >= {"id", "email"}
