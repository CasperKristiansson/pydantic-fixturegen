from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import doctor as doctor_mod
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.strategies import Strategy, StrategyBuilder, UnionStrategy
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _make_builder() -> StrategyBuilder:
    registry = create_default_registry(load_plugins=False)
    return StrategyBuilder(registry, plugin_manager=doctor_mod.get_plugin_manager())


def _write_module(tmp_path: Path, name: str = "models") -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str


class User(BaseModel):
    name: str
    age: int
    address: Address
""",
        encoding="utf-8",
    )
    return module_path


def test_doctor_basic(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "Coverage: 3/3 fields" in result.stdout
    assert "Issues: none" in result.stdout
    assert "Type coverage gaps: none" in result.stdout


def test_doctor_reports_unknown_extra_type(tmp_path: Path) -> None:
    module_path = tmp_path / "extra_models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class FakeExtra(str):
    pass


FakeExtra.__module__ = "pydantic_extra_types.fake"


class Payload(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    token: FakeExtra
""",
        encoding="utf-8",
    )

    result = runner.invoke(cli_app, ["doctor", str(module_path)])

    assert result.exit_code == 0
    assert "pydantic-extra-types" in result.stdout
    assert "FakeExtra" in result.stdout


def test_doctor_reports_provider_issue(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Note(BaseModel):
    payload: object
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        ["doctor", str(module_path)],
    )

    assert result.exit_code == 0
    assert "No provider registered" in result.stdout


def test_doctor_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        ["doctor", "--json-errors", str(missing)],
    )

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout


def test_doctor_fail_on_gaps_exits_with_code_two(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Broken(BaseModel):
    payload: object
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        [
            "doctor",
            "--fail-on-gaps",
            "0",
            str(module_path),
        ],
    )

    assert result.exit_code == 2


def test_execute_doctor_path_checks(tmp_path: Path) -> None:
    not_there = tmp_path / "missing.py"
    with pytest.raises(DiscoveryError):
        doctor_mod._execute_doctor(
            target=str(not_there),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=256,
        )

    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(DiscoveryError):
        doctor_mod._execute_doctor(
            target=str(directory),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=256,
        )


def test_doctor_warnings_and_no_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = tmp_path / "empty.py"
    module.write_text("", encoding="utf-8")

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[], warnings=["unused", "   "], errors=[])

    monkeypatch.setattr(doctor_mod, "discover_models", fake_discover)
    monkeypatch.setattr(doctor_mod, "clear_module_cache", lambda: None)

    doctor_mod._execute_doctor(
        target=str(module),
        include=None,
        exclude=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=1.0,
        memory_limit_mb=128,
    )

    captured = capsys.readouterr()
    assert "warning: unused" in captured.err
    assert "No models discovered." in captured.out


def test_prepare_doctor_target_requires_openapi_with_routes() -> None:
    with pytest.raises(DiscoveryError):
        doctor_mod._prepare_doctor_target(
            path_arg=None,
            schema=None,
            openapi=None,
            routes=["GET /users"],
        )


def test_prepare_doctor_target_schema(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{}", encoding="utf-8")
    generated = tmp_path / "generated.py"

    class DummyIngester:
        def ingest_json_schema(self, _: Path) -> SimpleNamespace:
            return SimpleNamespace(path=generated)

    monkeypatch.setattr(doctor_mod, "SchemaIngester", lambda: DummyIngester())

    target, includes = doctor_mod._prepare_doctor_target(
        path_arg=None,
        schema=schema_path,
        openapi=None,
        routes=None,
    )

    assert target == generated
    assert includes == []


def test_prepare_doctor_target_openapi_with_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    openapi_path = tmp_path / "spec.yaml"
    openapi_path.write_text("openapi: 3.0.0", encoding="utf-8")
    generated = tmp_path / "openapi_models.py"

    class DummySelection:
        def __init__(self, parsed_routes) -> None:
            self.document = {"paths": {}}
            self.schemas = ("User",)
            self.routes = tuple(parsed_routes or [])

        def fingerprint(self) -> str:
            return "sig"

    class DummyIngester:
        def ingest_openapi(self, *args, **kwargs) -> SimpleNamespace:  # noqa: ARG002
            return SimpleNamespace(path=generated)

    monkeypatch.setattr(doctor_mod, "SchemaIngester", lambda: DummyIngester())
    monkeypatch.setattr(
        doctor_mod,
        "load_openapi_document",
        lambda path: {"paths": {"/users": {"get": {}}}},
    )
    monkeypatch.setattr(
        doctor_mod,
        "select_openapi_schemas",
        lambda document, routes: DummySelection(routes),
    )
    monkeypatch.setattr(doctor_mod, "dump_document", lambda document: b"doc")

    target, includes = doctor_mod._prepare_doctor_target(
        path_arg=None,
        schema=None,
        openapi=openapi_path,
        routes=["GET /users"],
    )

    assert target == generated
    assert includes == ["*.User"]


def test_prepare_doctor_target_invalid_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    openapi_path = tmp_path / "spec.yaml"
    openapi_path.write_text("openapi: 3.0.0", encoding="utf-8")

    monkeypatch.setattr(
        doctor_mod,
        "load_openapi_document",
        lambda path: {"paths": {"/users": {"get": {}}}},
    )

    with pytest.raises(DiscoveryError):
        doctor_mod._prepare_doctor_target(
            path_arg=None,
            schema=None,
            openapi=openapi_path,
            routes=["INVALID"],
        )


def test_doctor_resolve_method_conflict() -> None:
    with pytest.raises(DiscoveryError):
        doctor_mod._resolve_method(ast_mode=True, hybrid_mode=True)


def test_doctor_resolve_method_variants() -> None:
    assert doctor_mod._resolve_method(ast_mode=False, hybrid_mode=True) == "hybrid"
    assert doctor_mod._resolve_method(ast_mode=True, hybrid_mode=False) == "ast"
    assert doctor_mod._resolve_method(ast_mode=False, hybrid_mode=False) == "import"


def test_doctor_load_model_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    info = IntrospectedModel(
        module="pkg",
        name="Missing",
        qualname="pkg.Missing",
        locator=str(module),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    monkeypatch.setattr(doctor_mod, "discover_models", fake_discover)
    monkeypatch.setattr(doctor_mod, "clear_module_cache", lambda: None)

    def boom_loader(_: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(doctor_mod, "load_model_class", boom_loader)

    with pytest.raises(DiscoveryError, match="boom"):
        doctor_mod._execute_doctor(
            target=str(module),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
        )


def test_doctor_render_report_with_issues(capsys: pytest.CaptureFixture[str]) -> None:
    class Dummy(BaseModel):
        value: int

    report = doctor_mod.ModelReport(
        model=Dummy,
        coverage=(1, 2),
        issues=["problem"],
        gaps=[
            doctor_mod.FieldGap(
                model=Dummy,
                field="value",
                info=doctor_mod.GapInfo(
                    type_name="int",
                    reason="No provider registered for type 'int'.",
                    remediation="Fix",
                    severity="error",
                ),
            )
        ],
    )

    gap_summary = doctor_mod.GapSummary(
        summaries=[
            doctor_mod.TypeGapSummary(
                type_name="int",
                reason="No provider registered for type 'int'.",
                remediation="Fix",
                severity="error",
                occurrences=1,
                fields=["Dummy.value"],
            )
        ],
        total_error_fields=1,
        total_warning_fields=0,
    )

    doctor_mod._render_report([report], gap_summary)
    captured = capsys.readouterr()
    assert "Coverage: 1/2" in captured.out
    assert "problem" in captured.out
    assert "Type coverage gaps" in captured.out
    assert "Dummy.value" in captured.out


def test_doctor_strategy_status_any_type() -> None:
    summary = FieldSummary(type="any", constraints=FieldConstraints())
    strategy = Strategy(
        field_name="sample",
        summary=summary,
        annotation=object,
        provider_ref=object(),
        provider_name="generic",
        provider_kwargs={},
        p_none=0.0,
    )
    covered, issues = doctor_mod._strategy_status(summary, strategy)
    assert covered is True
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "Falls back" in issues[0].reason


def test_strategy_status_provider_missing() -> None:
    summary = FieldSummary(type="uuid", constraints=FieldConstraints())
    strategy = Strategy(
        field_name="identifier",
        summary=summary,
        annotation=object,
        provider_ref=None,
        provider_name="uuid",
        provider_kwargs={},
        p_none=0.0,
    )
    covered, issues = doctor_mod._strategy_status(summary, strategy)
    assert covered is False
    assert issues[0].severity == "error"
    assert "No provider" in issues[0].reason


def test_strategy_status_union_propagates_gaps() -> None:
    summary_union = FieldSummary(type="union", constraints=FieldConstraints())
    summary_any = FieldSummary(type="any", constraints=FieldConstraints())
    choice_warning = Strategy(
        field_name="value",
        summary=summary_any,
        annotation=object,
        provider_ref=object(),
        provider_name="generic",
        provider_kwargs={},
        p_none=0.0,
    )
    choice_error = Strategy(
        field_name="value",
        summary=FieldSummary(type="custom", constraints=FieldConstraints()),
        annotation=object,
        provider_ref=None,
        provider_name="custom",
        provider_kwargs={},
        p_none=0.0,
    )
    union = UnionStrategy(
        field_name="value", choices=[choice_warning, choice_error], policy="first"
    )

    covered, issues = doctor_mod._strategy_status(summary_union, union)
    assert covered is False
    severities = {info.severity for info in issues}
    assert severities == {"warning", "error"}


def test_strategy_status_enum_values() -> None:
    summary = FieldSummary(type="enum", constraints=FieldConstraints(), enum_values=["a"])
    strategy = Strategy(
        field_name="value",
        summary=summary,
        annotation=str,
        provider_ref=None,
        provider_name="enum.static",
        provider_kwargs={},
        p_none=0.0,
        enum_values=["a"],
    )
    covered, issues = doctor_mod._strategy_status(summary, strategy)
    assert covered is True
    assert issues == []


def test_doctor_fail_on_gaps_threshold(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Note(BaseModel):
    data: object
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        ["doctor", "--fail-on-gaps", "0", str(module_path)],
    )

    assert result.exit_code == 2
    combined = result.stdout + result.stderr
    assert "No provider registered" in combined


def test_summarize_gaps_groups_fields() -> None:
    class Dummy(BaseModel):
        value: int

    info_error = doctor_mod.GapInfo(
        type_name="int",
        reason="No provider registered for type 'int'.",
        remediation="Fix",
        severity="error",
    )
    info_warning = doctor_mod.GapInfo(
        type_name="any",
        reason="Falls back to generic `Any` provider.",
        remediation="Adjust",
        severity="warning",
    )

    gaps = [
        doctor_mod.FieldGap(model=Dummy, field="value", info=info_error),
        doctor_mod.FieldGap(model=Dummy, field="other", info=info_warning),
    ]

    summary = doctor_mod._summarize_gaps(gaps)

    assert summary.total_error_fields == 1
    assert summary.total_warning_fields == 1
    assert len(summary.summaries) == 2
    types = {item.type_name for item in summary.summaries}
    assert {"int", "any"} == types


def test_analyse_model_supported_field() -> None:
    class Person(BaseModel):
        name: str

    builder = _make_builder()
    report = doctor_mod._analyse_model(Person, builder)

    assert report.coverage == (1, 1)
    assert report.gaps == []


def test_analyse_model_any_field_records_warning() -> None:
    class Note(BaseModel):
        payload: object

    builder = _make_builder()
    report = doctor_mod._analyse_model(Note, builder)

    assert report.coverage == (0, 1)
    assert len(report.gaps) == 1
    assert report.gaps[0].info.severity == "error"


def test_analyse_model_strategy_status_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    class Sample(BaseModel):
        value: int

    builder = _make_builder()

    def fake_status(
        summary: FieldSummary, strategy: Strategy
    ) -> tuple[bool, list[doctor_mod.GapInfo]]:  # type: ignore[type-arg]
        return True, [
            doctor_mod.GapInfo(
                type_name=summary.type,
                reason="Synthetic warning",
                remediation="Handle",
                severity="warning",
            )
        ]

    monkeypatch.setattr(doctor_mod, "_strategy_status", fake_status)

    report = doctor_mod._analyse_model(Sample, builder)

    assert report.coverage == (1, 1)
    assert len(report.gaps) == 1
    assert report.gaps[0].info.reason == "Synthetic warning"


def test_execute_doctor_discovery_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        return IntrospectionResult(models=[], warnings=[], errors=["boom"])

    monkeypatch.setattr(doctor_mod, "discover_models", fake_discover)
    monkeypatch.setattr(doctor_mod, "clear_module_cache", lambda: None)

    with pytest.raises(DiscoveryError, match="boom"):
        doctor_mod._execute_doctor(
            target=str(module),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
        )


def test_doctor_handles_pfg_error_return(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_execute(**_: object) -> doctor_mod.GapSummary:  # type: ignore[override]
        raise DiscoveryError("boom")

    monkeypatch.setattr(doctor_mod, "_execute_doctor", fake_execute)
    monkeypatch.setattr(
        doctor_mod,
        "render_cli_error",
        lambda error, *, json_errors: captured.append(str(error)),
    )

    doctor_mod.doctor(
        None,
        path="ignored",
        include=None,
        exclude=None,
        schema=None,
        openapi=None,
        routes=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=1.0,
        memory_limit_mb=128,
        json_errors=False,
        fail_on_gaps=None,
    )

    assert captured == ["boom"]


def test_doctor_handles_schema_input(tmp_path: Path) -> None:
    schema_path = tmp_path / "user.schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "title": "User",
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_app,
        [
            "doctor",
            "--schema",
            str(schema_path),
        ],
    )

    assert result.exit_code == 0, result.stderr or result.output
    assert "User" in result.stdout
