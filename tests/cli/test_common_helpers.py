from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import typer
from pydantic import BaseModel
from pydantic_fixturegen.cli.gen import _common as common
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.introspect import IntrospectedModel


@pytest.fixture(autouse=True)
def _reset_module_cache() -> None:
    common._module_cache.clear()
    yield
    common._module_cache.clear()


def _write_module(tmp_path: Path, name: str = "sample") -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int


class Plain:
    pass
""",
        encoding="utf-8",
    )
    return path


def _model_info(path: Path, module_name: str, attr: str) -> IntrospectedModel:
    return IntrospectedModel(
        module=module_name,
        name=attr,
        qualname=f"{module_name}.{attr}",
        locator=str(path),
        lineno=1,
        discovery="import",
        is_public=True,
    )


def test_load_model_class_success(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    module = common._import_module_by_path("sample_module", module_path)
    assert module is common._module_cache["sample_module"]

    info = _model_info(module_path, "sample_module", "User")
    model_cls = common.load_model_class(info)
    assert issubclass(model_cls, BaseModel)


def test_load_model_class_invalid(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    common._import_module_by_path("sample_invalid", module_path)

    info = _model_info(module_path, "sample_invalid", "Plain")
    with pytest.raises(RuntimeError, match="not a Pydantic BaseModel"):
        common.load_model_class(info)


def test_render_cli_error_prints_hint(capsys: pytest.CaptureFixture[str]) -> None:
    error = DiscoveryError("missing", hint="install fixture")
    with pytest.raises(typer.Exit) as exc:
        common.render_cli_error(error, json_errors=False)
    assert exc.value.exit_code == 10
    captured = capsys.readouterr()
    assert "hint" in captured.err


def test_import_module_by_path_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    with pytest.raises(RuntimeError, match="Could not locate module"):
        common._import_module_by_path("missing_mod", missing)


def test_import_module_by_path_uses_existing_module(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, name="cached")
    module_name = "cached_mod"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    sys.modules[module_name] = module

    loaded = common._load_module(module_name, module_path)
    assert loaded is module
    assert common._module_cache[module_name] is module
    sys.modules.pop(module_name, None)


def test_import_module_by_path_name_conflict(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path, name="conflict")
    module_name = "conflict_mod"
    sys.modules[module_name] = types.ModuleType(module_name)

    loaded = common._import_module_by_path(module_name, module_path)
    assert loaded is common._module_cache[module_name]
    assert loaded.__file__
    sys.modules.pop(module_name, None)


def test_import_module_by_path_spec_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path, name="broken")

    def fake_spec(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr(common.importlib.util, "spec_from_file_location", fake_spec)
    with pytest.raises(RuntimeError, match="Failed to load module"):
        common._import_module_by_path("broken_mod", module_path)


def test_parse_relation_links_handles_multiple_sources() -> None:
    values = common.parse_relation_links(
        ["Order.user_id=User.id,Order.item_id=Item.id", "Invoice.customer_id=Customer.id"]
    )
    assert values == {
        "Order.user_id": "User.id",
        "Order.item_id": "Item.id",
        "Invoice.customer_id": "Customer.id",
    }


def test_parse_relation_links_requires_equals() -> None:
    with pytest.raises(typer.BadParameter):
        common.parse_relation_links(["missing-delimiter"])


def test_parse_override_entries_parses_json_payloads() -> None:
    entries = ('User.email={"value": "fixed@example.com"}',)
    result = common.parse_override_entries(entries)
    assert result["User"]["email"]["value"] == "fixed@example.com"


def test_parse_override_entries_rejects_invalid_payload() -> None:
    with pytest.raises(typer.BadParameter):
        common.parse_override_entries(["User.email={not-json}"])
