from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.api.models import ConfigSnapshot, JsonGenerationResult
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import openapi as openapi_module
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.logging import get_logger
from tests._cli import create_cli_runner

runner = create_cli_runner()

OPENAPI_SPEC = """
openapi: 3.0.0
info:
  title: Example
  version: 1.0.0
paths:
  /users:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserList"
  /orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/Order"
      responses:
        "201":
          description: Created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
components:
  schemas:
    UserList:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: "#/components/schemas/User"
    User:
      type: object
      properties:
        id:
          type: integer
        email:
          type: string
    Order:
      type: object
      required: ["id"]
      properties:
        id:
          type: integer
        total:
          type: number
"""


def test_gen_openapi_emits_per_schema(tmp_path: Path) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    output_template = tmp_path / "{model}.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--route",
            "GET /users",
            "--route",
            "POST /orders",
            "--out",
            str(output_template),
        ],
    )

    assert result.exit_code == 0, result.output
    user_list = json.loads((tmp_path / "UserList.json").read_text(encoding="utf-8"))
    assert isinstance(user_list, list) and user_list
    assert "items" in user_list[0]
    order = json.loads((tmp_path / "Order.json").read_text(encoding="utf-8"))
    assert isinstance(order, list) and order
    assert "id" in order[0]


def test_gen_openapi_requires_model_placeholder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    output_path = tmp_path / "samples.json"
    errors = _suppress_openapi_cli_exit(monkeypatch)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert errors and "must include '{model}'" in str(errors[0])


def _suppress_openapi_cli_exit(monkeypatch: pytest.MonkeyPatch) -> list[DiscoveryError]:
    original_render = openapi_module.render_cli_error
    captured: list[DiscoveryError] = []

    def patched(error: DiscoveryError, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original_render(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(openapi_module, "render_cli_error", patched)
    return captured


def test_gen_openapi_reports_selection_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    errors = _suppress_openapi_cli_exit(monkeypatch)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    def fail_selection(document: dict, routes: list[tuple[str, str]] | None) -> None:
        raise DiscoveryError("selection failed")

    monkeypatch.setattr(openapi_module, "select_openapi_schemas", fail_selection)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code == 0
    assert errors and "selection failed" in str(errors[0])


def test_gen_openapi_reports_template_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    errors = _suppress_openapi_cli_exit(monkeypatch)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    class BrokenTemplate(OutputTemplate):
        def __init__(self, *args, **kwargs) -> None:
            raise DiscoveryError("template issue")

    monkeypatch.setattr(openapi_module, "OutputTemplate", BrokenTemplate)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code == 0
    assert errors and "template issue" in str(errors[0])


def test_gen_openapi_skips_summary_when_snapshot_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    snapshot = ConfigSnapshot(seed=None, include=(), exclude=(), time_anchor=None)
    sample_result = JsonGenerationResult(
        paths=(tmp_path / "UserList.json",),
        base_output=tmp_path / "UserList.json",
        model=None,
        config=snapshot,
        constraint_summary=None,
        warnings=(),
        delegated=False,
    )

    def fake_generate(*args: object, **kwargs: object) -> JsonGenerationResult:
        return sample_result

    def fake_snapshot(logger: object, result: JsonGenerationResult, count: int) -> bool:
        return True

    monkeypatch.setattr(openapi_module, "_generate_for_schema", fake_generate)
    monkeypatch.setattr(openapi_module, "_log_generation_snapshot", fake_snapshot)

    echoed: list[str] = []
    monkeypatch.setattr(openapi_module.typer, "echo", lambda message: echoed.append(str(message)))

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
            "--route",
            "GET /users",
        ],
    )

    assert result.exit_code == 0
    assert echoed == []


def test_generate_for_schema_wraps_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        openapi_module,
        "generate_json_artifacts",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    template = OutputTemplate(str(tmp_path / "{model}.json"))

    with pytest.raises(EmitError):
        openapi_module._generate_for_schema(
            "UserList",
            module_path=tmp_path / "module.py",
            include_pattern="*.UserList",
            output_template=template,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
            respect_validators=None,
            validator_max_retries=None,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            logger=get_logger(),
        )


def test_gen_openapi_handles_invalid_route_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    errors = _suppress_openapi_cli_exit(monkeypatch)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--route",
            "INVALID",
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code == 0
    assert errors


def test_gen_openapi_reports_ingest_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    errors = _suppress_openapi_cli_exit(monkeypatch)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    class DummyIngester:
        def ingest_openapi(self, *args: object, **kwargs: object) -> None:
            raise DiscoveryError("ingest failure")

    monkeypatch.setattr(openapi_module, "SchemaIngester", DummyIngester)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code == 0
    assert errors and "ingest failure" in str(errors[0])


def test_gen_openapi_reports_generation_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    errors = _suppress_openapi_cli_exit(monkeypatch)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    monkeypatch.setattr(
        openapi_module,
        "_generate_for_schema",
        lambda *args, **kwargs: (_ for _ in ()).throw(DiscoveryError("generation boom")),
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code == 0
    assert errors and "generation boom" in str(errors[0])


def test_gen_openapi_handles_ingester_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    def fail_ingest(self, *args, **kwargs):
        raise openapi_module.DiscoveryError("ingest failed")

    monkeypatch.setattr(openapi_module.SchemaIngester, "ingest_openapi", fail_ingest)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(tmp_path / "{model}.json"),
        ],
    )

    assert result.exit_code != 0
    assert "ingest failed" in result.stderr


def test_generate_for_schema_reports_generation_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text("from pydantic import BaseModel\n", encoding="utf-8")
    template = OutputTemplate(str(tmp_path / "{model}.json"))
    logger = get_logger()

    def fail_generate(**kwargs):
        raise openapi_module.EmitError("boom")

    monkeypatch.setattr(openapi_module, "generate_json_artifacts", fail_generate)
    handled: list[str] = []

    def record_error(logger_arg, exc):
        handled.append(str(exc))

    monkeypatch.setattr(openapi_module, "_handle_generation_error", record_error)

    with pytest.raises(openapi_module.EmitError):
        openapi_module._generate_for_schema(
            "User",
            module_path=module_path,
            include_pattern="*.User",
            output_template=template,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
            respect_validators=None,
            validator_max_retries=None,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
            logger=logger,
        )

    assert handled == ["boom"]
