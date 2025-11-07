from __future__ import annotations

import dataclasses
import decimal
import enum
import json
import math
from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import explain as explain_mod
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.strategies import Strategy, StrategyBuilder, UnionStrategy
from tests._cli import create_cli_runner

runner = create_cli_runner()


@dataclasses.dataclass
class SampleInner:
    value: int = 5


@dataclasses.dataclass
class SampleOuter:
    inner: SampleInner
    optional: SampleInner | None = None
    values: list[int] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TruncatedChild:
    value: int


@dataclasses.dataclass
class TruncatedParent:
    child: TruncatedChild


class SampleEnum(enum.Enum):
    A = "a"


class UnionModel(BaseModel):
    choice: int | str


class WrapperModel(BaseModel):
    inner: SampleInner


class SimpleModel(BaseModel):
    value: int


@dataclasses.dataclass
class ModelCarrier:
    model: SimpleModel


def _write_models(tmp_path: Path) -> Path:
    module = tmp_path / "models.py"
    module.write_text(
        """
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass
class Address:
    city: str
    country: str = "SE"


class Profile(BaseModel):
    username: str
    active: bool
    address: Address


class User(BaseModel):
    name: str
    age: int
    profile: Profile
    role: Literal["admin", "user"]
""",
        encoding="utf-8",
    )
    return module


def test_explain_outputs_summary(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(cli_app, ["gen", "explain", str(module)])

    assert result.exit_code == 0
    stdout = result.stdout
    assert "Model: models.User" in stdout
    assert "Field: profile" in stdout
    assert "Nested model: models.Profile" in stdout
    assert "Nested model: models.Address" in stdout
    assert "Field: country" in stdout
    assert "Default: SE" in stdout
    assert "Field: role" in stdout


def test_explain_json_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = runner.invoke(cli_app, ["gen", "explain", "--json-errors", str(missing)])

    assert result.exit_code == 10
    assert "DiscoveryError" in result.stdout


def test_explain_json_mode(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(cli_app, ["gen", "explain", "--json", str(module)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["warnings"] == []
    user = next(model for model in payload["models"] if model["name"] == "User")
    fields = {field["name"]: field for field in user["fields"]}
    assert "profile" in fields
    assert fields["profile"]["strategy"]["kind"] == "provider"
    profile_nested = fields["profile"]["strategy"]["nested_model"]
    address_field = next(field for field in profile_nested["fields"] if field["name"] == "address")
    address_strategy = address_field["strategy"]
    address_nested = address_strategy["nested_model"]
    assert address_nested["kind"] == "dataclass"
    dataclass_fields = {field["name"]: field for field in address_nested["fields"]}
    assert dataclass_fields["country"]["summary"]["default"] == "SE"


def test_explain_tree_mode(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(cli_app, ["gen", "explain", "--tree", str(module)])

    assert result.exit_code == 0
    stdout = result.stdout
    assert "Model models.User" in stdout
    assert "|-- field profile" in stdout
    assert "provider" in stdout
    assert "nested models.Address" in stdout
    assert "field country" in stdout


def test_explain_max_depth_limit(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(cli_app, ["gen", "explain", "--tree", "--max-depth", "0", str(module)])

    assert result.exit_code == 0
    assert "... (max depth reached)" in result.stdout


def test_execute_explain_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = tmp_path / "empty.py"
    module.write_text("", encoding="utf-8")

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[], warnings=["unused"], errors=[])

    monkeypatch.setattr(explain_mod, "discover_models", fake_discover)
    monkeypatch.setattr(explain_mod, "clear_module_cache", lambda: None)

    result = runner.invoke(cli_app, ["gen", "explain", str(module)])

    assert result.exit_code == 0
    assert "warning: unused" in result.stderr
    assert "No models discovered." in result.stdout


def test_execute_explain_union_and_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    info = IntrospectedModel(
        module="pkg",
        name="Demo",
        qualname="pkg.Demo",
        locator=str(module),
        lineno=1,
        discovery="import",
        is_public=True,
    )

    class DemoModel(BaseModel):
        name: str
        fails: int
        role: str

    def fake_discover(path: Path, **_: object) -> IntrospectionResult:
        assert path == module
        return IntrospectionResult(models=[info], warnings=[], errors=[])

    monkeypatch.setattr(explain_mod, "discover_models", fake_discover)
    monkeypatch.setattr(explain_mod, "load_model_class", lambda _: DemoModel)
    monkeypatch.setattr(explain_mod, "clear_module_cache", lambda: None)
    monkeypatch.setattr(explain_mod, "create_default_registry", lambda load_plugins: object())

    class DummyBuilder:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def build_field_strategy(self, model, field_name, annotation, summary):  # noqa: ANN001, ANN201
            base_summary = FieldSummary(type="string", constraints=FieldConstraints())
            if field_name == "fails":
                raise ValueError("no provider")
            if field_name == "role":
                choice = Strategy(
                    field_name="role",
                    summary=base_summary,
                    annotation=str,
                    provider_ref=None,
                    provider_name="string.default",
                    provider_kwargs={},
                    p_none=0.0,
                )
                return UnionStrategy(field_name="role", choices=[choice], policy="first")
            return Strategy(
                field_name=field_name,
                summary=base_summary,
                annotation=str,
                provider_ref=None,
                provider_name="string.default",
                provider_kwargs={},
                p_none=0.0,
            )

    monkeypatch.setattr(explain_mod, "StrategyBuilder", lambda *args, **kwargs: DummyBuilder())

    result = runner.invoke(cli_app, ["gen", "explain", str(module)])

    assert result.exit_code == 0
    stdout = result.stdout
    assert "test_execute_explain_union_and_failures.<locals>.DemoModel" in stdout
    assert "Field: fails" in stdout
    assert "Issue: no provider" in stdout
    assert "Union policy" in stdout


def test_explain_rejects_json_and_tree(tmp_path: Path) -> None:
    module = _write_models(tmp_path)

    result = runner.invoke(cli_app, ["gen", "explain", "--json", "--tree", str(module)])

    assert result.exit_code == 10
    assert "--json and --tree cannot be combined" in result.stderr


def test_collect_dataclass_report_expands_nested() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_dataclass_report(
        SampleOuter,
        builder=builder,
        max_depth=None,
        visited=set(),
    )

    assert report["kind"] == "dataclass"
    fields = {field["name"]: field for field in report["fields"]}
    assert "SampleInner" in fields["inner"]["summary"]["annotation"]
    assert "SampleInner" in fields["optional"]["summary"]["annotation"]
    assert "list" in fields["values"]["summary"].get("default_factory", "")
    nested = fields["inner"].get("nested")
    assert nested and nested["kind"] == "dataclass"
    nested_fields = {field["name"]: field for field in nested["fields"]}
    assert nested_fields["value"]["summary"]["default"] == 5


def test_collect_dataclass_report_truncated() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_dataclass_report(
        TruncatedParent,
        builder=builder,
        max_depth=0,
        visited=set(),
    )

    field_entry = report["fields"][0]
    assert field_entry["truncated"] is True


def test_collect_dataclass_report_detects_cycle() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_dataclass_report(
        SampleInner,
        builder=builder,
        max_depth=None,
        visited={SampleInner},
    )

    assert report["cycle"] is True


def test_collect_dataclass_report_marks_unsupported() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_dataclass_report(
        SampleEnum,
        builder=builder,
        max_depth=None,
        visited=set(),
    )

    assert report["unsupported"] is True


def test_collect_dataclass_report_includes_nested_model() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_dataclass_report(
        ModelCarrier,
        builder=builder,
        max_depth=None,
        visited=set(),
    )

    field_entry = report["fields"][0]
    nested = field_entry.get("nested")
    assert nested and nested["kind"] == "model"


def test_collect_model_report_detects_cycle() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    report = explain_mod._collect_model_report(
        SimpleModel,
        builder=builder,
        max_depth=None,
        visited={SimpleModel},
    )

    assert report["cycle"] is True


def test_collect_model_report_records_strategy_errors() -> None:
    class FailingBuilder:
        def build_field_strategy(self, *args, **kwargs):  # noqa: ANN001, ANN201
            raise ValueError("unavailable")

    report = explain_mod._collect_model_report(
        SimpleModel,
        builder=FailingBuilder(),
        max_depth=None,
        visited=set(),
    )

    field_entry = report["fields"][0]
    assert field_entry["error"] == "unavailable"


def test_strategy_to_payload_union_truncated() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))
    strategies = builder.build_model_strategies(UnionModel)

    union_strategy = strategies["choice"]
    assert isinstance(union_strategy, UnionStrategy)

    payload = explain_mod._strategy_to_payload(
        union_strategy,
        builder=builder,
        remaining_depth=0,
        visited=set(),
    )

    assert payload["kind"] == "union"
    assert payload["truncated"] is True


def test_strategy_to_payload_nested_dataclass() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))
    strategies = builder.build_model_strategies(WrapperModel)

    strategy = strategies["inner"]
    payload = explain_mod._strategy_to_payload(
        strategy,
        builder=builder,
        remaining_depth=1,
        visited=set(),
    )

    nested = payload.get("nested_model")
    assert nested and nested["kind"] == "dataclass"
    assert nested["qualname"].endswith("SampleInner")


def test_strategy_to_payload_includes_provider_metadata() -> None:
    summary = FieldSummary(type="enum", constraints=FieldConstraints(), enum_values=["x", "y"])
    strategy = Strategy(
        field_name="flag",
        summary=summary,
        annotation=str,
        provider_ref=None,
        provider_name="string.custom",
        provider_kwargs={"min_length": 2},
        p_none=0.1,
        enum_values=["x", "y"],
        enum_policy="random",
    )
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    payload = explain_mod._strategy_to_payload(
        strategy,
        builder=builder,
        remaining_depth=None,
        visited=set(),
    )

    assert payload["enum_values"] == ["x", "y"]
    assert payload["enum_policy"] == "random"
    assert payload["provider_kwargs"] == {"min_length": 2}


def test_render_field_text_handles_error_and_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(explain_mod.typer, "echo", lambda message: captured.append(message))

    explain_mod._render_field_text(
        {
            "name": "problem",
            "summary": {"type": "string"},
            "error": "boom",
        },
        indent="",
    )

    assert any("Issue: boom" in line for line in captured)

    captured.clear()
    explain_mod._render_field_text(
        {
            "name": "trunc",
            "summary": {"type": "string"},
            "truncated": True,
        },
        indent="  ",
    )

    assert any("... (max depth reached)" in line for line in captured)


def test_render_strategy_text_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(explain_mod.typer, "echo", lambda message: captured.append(message))

    explain_mod._render_strategy_text(
        {
            "kind": "union",
            "policy": "random",
            "options": [
                {
                    "index": 1,
                    "summary": {"type": "int"},
                    "strategy": {
                        "kind": "provider",
                        "provider": "int.static",
                    },
                }
            ],
        },
        indent="",
    )

    assert any("Union policy: random" in line for line in captured)
    assert any("Option 1 -> type: int" in line for line in captured)

    captured.clear()
    explain_mod._render_strategy_text(
        {
            "kind": "provider",
            "provider": "string.default",
            "p_none": 0.5,
            "enum_values": ["a", "b"],
            "enum_policy": "random",
            "provider_kwargs": {"min_length": 1},
            "nested_model": {
                "qualname": "pkg.Model",
                "fields": [
                    {"name": "field", "summary": {"type": "string"}},
                ],
            },
        },
        indent="  ",
    )

    assert any("Provider: string.default" in line for line in captured)
    assert any("p_none: 0.5" in line for line in captured)
    assert any("Enum values: ['a', 'b']" in line for line in captured)
    assert any("Nested model: pkg.Model" in line for line in captured)


def test_render_strategy_text_union_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(explain_mod.typer, "echo", lambda message: captured.append(message))

    explain_mod._render_strategy_text(
        {"kind": "union", "policy": "first", "truncated": True},
        indent="",
    )

    assert any("... (max depth reached)" in line for line in captured)


def test_constraints_to_dict_formats_all_fields() -> None:
    constraints = FieldConstraints(
        ge=1.0,
        le=5.0,
        gt=0.0,
        lt=10.0,
        multiple_of=decimal.Decimal("0.5"),
        min_length=2,
        max_length=8,
        pattern="^x",
        max_digits=6,
        decimal_places=2,
    )
    summary = FieldSummary(type="string", constraints=constraints)

    result = explain_mod._constraints_to_dict(summary)

    assert result["ge"] == pytest.approx(1.0)
    assert result["multiple_of"] == pytest.approx(0.5)
    assert result["pattern"] == "^x"
    assert result["decimal_places"] == 2


def test_summary_to_payload_includes_optional_fields() -> None:
    summary = FieldSummary(
        type="collection",
        constraints=FieldConstraints(),
        format="json",
        item_type="int",
        enum_values=[1, 2],
        is_optional=True,
    )

    payload = explain_mod._summary_to_payload(summary)

    assert payload["type"] == "collection"
    assert payload["is_optional"] is True
    assert payload["format"] == "json"
    assert payload["item_type"] == "int"
    assert payload["enum_values"] == [1, 2]


def test_render_tree_outputs_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(explain_mod.typer, "echo", lambda message: captured.append(message))

    explain_mod._render_tree(
        [
            {
                "qualname": "pkg.Model",
                "fields": [
                    {
                        "name": "choice",
                        "summary": {"type": "union"},
                        "strategy": {
                            "kind": "union",
                            "policy": "random",
                            "options": [
                                {
                                    "index": 1,
                                    "summary": {"type": "int"},
                                    "strategy": {
                                        "kind": "provider",
                                        "provider": "int.static",
                                        "truncated": True,
                                    },
                                },
                                {
                                    "index": 2,
                                    "summary": {"type": "model"},
                                    "strategy": {
                                        "kind": "provider",
                                        "provider": "model.provider",
                                        "nested_model": {"qualname": "pkg.Cycle", "cycle": True},
                                    },
                                },
                            ],
                        },
                    },
                    {
                        "name": "simple",
                        "summary": {"type": "string"},
                        "strategy": {
                            "kind": "provider",
                            "provider": "string.default",
                            "p_none": 0.2,
                            "enum_values": ["a"],
                            "enum_policy": "first",
                            "provider_kwargs": {"min_length": 1},
                            "nested_model": {"qualname": "pkg.Unsupported", "unsupported": True},
                        },
                        "truncated": True,
                    },
                    {
                        "name": "error_field",
                        "summary": {"type": "int"},
                        "error": "failing provider",
                    },
                ],
            }
        ]
    )

    assert any("Model pkg.Model" in line for line in captured)
    assert any("field choice" in line for line in captured)
    assert any("union policy=random" in line for line in captured)
    assert any("provider string.default" in line for line in captured)
    assert any("error: failing provider" in line for line in captured)


def test_resolve_runtime_type_variants() -> None:
    optional_type = explain_mod._resolve_runtime_type(SampleInner | None)
    assert optional_type is SampleInner

    annotated_type = explain_mod._resolve_runtime_type(
        Annotated[SampleInner, "meta"]  # type: ignore[name-defined]
    )
    assert annotated_type is SampleInner

    assert explain_mod._resolve_runtime_type(list[int]) is None


def test_explain_handles_pfg_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    def raise_error(**_: object) -> dict[str, Any]:
        raise DiscoveryError("boom")

    monkeypatch.setattr(explain_mod, "_execute_explain", raise_error)

    result = runner.invoke(cli_app, ["gen", "explain", str(module)])

    assert result.exit_code == 10
    combined = result.stdout + result.stderr
    assert "boom" in combined


def test_explain_handles_value_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    def raise_value(**_: object) -> dict[str, Any]:
        raise ValueError("bad args")

    monkeypatch.setattr(explain_mod, "_execute_explain", raise_value)

    result = runner.invoke(cli_app, ["gen", "explain", str(module)])

    assert result.exit_code == 10
    combined = result.stdout + result.stderr
    assert "bad args" in combined


def test_explain_callback_returns_after_pfg_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        explain_mod,
        "render_cli_error",
        lambda error, *, json_errors, exit_app=True: captured.setdefault("msg", str(error)),  # noqa: ARG005
    )
    monkeypatch.setattr(
        explain_mod,
        "_execute_explain",
        lambda **_: (_ for _ in ()).throw(DiscoveryError("callback boom")),
    )

    explain_mod.explain(
        None,
        path=str(module),
        include=None,
        exclude=None,
        json_output=False,
        tree_mode=False,
        max_depth=None,
        json_errors=False,
    )

    assert captured["msg"] == "callback boom"


def test_explain_callback_returns_after_value_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = tmp_path / "models.py"
    module.write_text("", encoding="utf-8")

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        explain_mod,
        "render_cli_error",
        lambda error, *, json_errors, exit_app=True: captured.setdefault("msg", str(error)),  # noqa: ARG005
    )
    monkeypatch.setattr(
        explain_mod,
        "_execute_explain",
        lambda **_: (_ for _ in ()).throw(ValueError("callback bad")),
    )

    explain_mod.explain(
        None,
        path=str(module),
        include=None,
        exclude=None,
        json_output=False,
        tree_mode=False,
        max_depth=None,
        json_errors=False,
    )

    assert captured["msg"] == "callback bad"


def test_safe_json_handles_nested_values() -> None:
    class FailingDecimal(decimal.Decimal):
        def __new__(cls, value: str) -> FailingDecimal:
            return decimal.Decimal.__new__(cls, value)

        def __float__(self) -> float:
            raise OverflowError

    payload = {
        "enum": SampleEnum.A,
        "decimal": decimal.Decimal("1.25"),
        "huge": decimal.Decimal("1e9999"),
        "sequence": {decimal.Decimal("2.5"), SampleEnum.A},
        "mapping": {"inner": decimal.Decimal("3.5")},
        "failing": FailingDecimal("42"),
    }

    result = explain_mod._safe_json(payload)

    assert result["enum"] == "a"
    assert result["decimal"] == pytest.approx(1.25)
    assert math.isinf(result["huge"])
    assert set(result["sequence"]) == {2.5, "a"}
    assert result["mapping"]["inner"] == pytest.approx(3.5)
    assert result["failing"] == str(FailingDecimal("42"))

    assert explain_mod._resolve_runtime_type(SampleInner | TruncatedChild) is None


def test_describe_callable_outputs() -> None:
    def factory() -> list[int]:  # noqa: D401
        return []

    described = explain_mod._describe_callable(factory)
    assert factory.__name__ in described

    lambda_result = explain_mod._describe_callable(lambda: None)
    assert lambda_result


def test_safe_json_complex_values() -> None:
    mapping = {"enum": SampleEnum.A, "decimal": decimal.Decimal("1.5")}
    result = explain_mod._safe_json(mapping)
    assert result["enum"] == "a"
    assert result["decimal"] == 1.5

    collection = explain_mod._safe_json({1, 2})
    assert sorted(collection) == [1, 2]


def test_field_to_tree_nested_and_truncated() -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))
    nested = explain_mod._collect_dataclass_report(
        SampleInner,
        builder=builder,
        max_depth=None,
        visited=set(),
    )

    field = {
        "name": "inner",
        "summary": {"type": "SampleInner"},
        "nested": nested,
    }
    node = explain_mod._field_to_tree(field)
    assert node.children and node.children[0].label.startswith("nested")

    truncated_field = {
        "name": "trimmed",
        "summary": {"type": "SampleInner"},
        "truncated": True,
    }
    truncated_node = explain_mod._field_to_tree(truncated_field)
    assert truncated_node.children and truncated_node.children[0].label.startswith("... (max")


def test_strategy_to_tree_node_union_truncated() -> None:
    node = explain_mod._strategy_to_tree_node({"kind": "union", "policy": "random", "truncated": True})
    assert node.children and node.children[0].label == "... (max depth reached)"


def test_render_field_text_truncated(capsys: pytest.CaptureFixture[str]) -> None:
    field = {
        "name": "trimmed",
        "summary": {"type": "SampleInner"},
        "truncated": True,
    }
    explain_mod._render_field_text(field, indent="")
    out = capsys.readouterr().out
    assert "... (max depth reached)" in out


def test_render_field_text_nested_dataclass(capsys: pytest.CaptureFixture[str]) -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))
    nested = explain_mod._collect_dataclass_report(
        SampleInner,
        builder=builder,
        max_depth=None,
        visited=set(),
    )
    field = {
        "name": "inner",
        "summary": {"type": "SampleInner"},
        "nested": nested,
    }
    explain_mod._render_field_text(field, indent="")
    out = capsys.readouterr().out
    assert "Nested model" in out


def test_render_field_text_rich_summary(capsys: pytest.CaptureFixture[str]) -> None:
    field = {
        "name": "rich",
        "summary": {
            "type": "string",
            "format": "email",
            "is_optional": True,
            "constraints": {"min_length": 1},
            "default": "user@example.com",
            "default_factory": "factory()",
        },
    }
    explain_mod._render_field_text(field, indent="")
    out = capsys.readouterr().out
    assert "Format: email" in out
    assert "Optional: True" in out
    assert "Constraints: {'min_length': 1}" in out
    assert "Default: user@example.com" in out
    assert "Default factory: factory()" in out


def test_render_nested_model_text_special_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(explain_mod.typer, "echo", lambda message: captured.append(message))

    explain_mod._render_nested_model_text({"qualname": "pkg.Model", "cycle": True}, indent="")
    explain_mod._render_nested_model_text({"qualname": "pkg.Other", "unsupported": True}, indent="")

    assert "cycle detected" in captured[0]
    assert "not expanded" in captured[1]


def test_collect_dataclass_report_fields_error(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = StrategyBuilder(create_default_registry(load_plugins=False))

    original_fields = dataclasses.fields

    def fake_fields(cls: type[Any]) -> tuple[Any, ...]:  # noqa: ANN401
        if cls is SampleInner:
            raise TypeError("broken")
        return original_fields(cls)

    monkeypatch.setattr(dataclasses, "fields", fake_fields)

    report = explain_mod._collect_dataclass_report(
        SampleInner,
        builder=builder,
        max_depth=None,
        visited=set(),
    )

    assert report["unsupported"] is True
