from __future__ import annotations

import dataclasses
import decimal
import enum
import json
from pathlib import Path
from typing import Annotated

import pytest
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import explain as explain_mod
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.strategies import Strategy, StrategyBuilder, UnionStrategy
from typer.testing import CliRunner

runner = CliRunner()


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


def test_resolve_runtime_type_variants() -> None:
    optional_type = explain_mod._resolve_runtime_type(SampleInner | None)
    assert optional_type is SampleInner

    annotated_type = explain_mod._resolve_runtime_type(
        Annotated[SampleInner, "meta"]  # type: ignore[name-defined]
    )
    assert annotated_type is SampleInner

    assert explain_mod._resolve_runtime_type(list[int]) is None
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
