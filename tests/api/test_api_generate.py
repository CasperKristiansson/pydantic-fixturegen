from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from pydantic_fixturegen import api as api_module
from pydantic_fixturegen.core.errors import EmitError


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel, Field


class Address(BaseModel):
    city: str
    postcode: str = Field(min_length=3)


class User(BaseModel):
    name: str
    age: int
    address: Address


class Order(BaseModel):
    order_id: str
    total: float
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


def test_generate_json_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_template = tmp_path / "artifacts" / "{model}" / "sample-{case_index}"

    result = api_module.generate_json(
        module_path,
        out=out_template,
        count=2,
        shard_size=1,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.model is not None and result.model.__name__ == "User"
    assert len(result.paths) == 2
    assert all(path.exists() for path in result.paths)
    records = [json.loads(path.read_text(encoding="utf-8")) for path in result.paths]
    assert len(records) == 2
    assert result.config.include == ("models.User",)


def test_generate_fixtures_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "fixtures" / "{model}" / "fixtures.py"

    result = api_module.generate_fixtures(
        module_path,
        out=output,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.path is not None and result.path.exists()
    text = result.path.read_text(encoding="utf-8")
    assert "def user(" in text
    assert not result.skipped


def test_generate_schema_api(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schemas" / "{model}" / "schema.json"

    result = api_module.generate_schema(
        module_path,
        out=output,
        include=["models.User"],
    )

    assert not result.delegated
    assert result.path is not None and result.path.exists()
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["title"] == "User"


def test_generate_json_with_freeze_seeds(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    out_template = tmp_path / "out" / "{model}.json"
    freeze_file = tmp_path / "seeds.json"

    result = api_module.generate_json(
        module_path,
        out=out_template,
        include=["models.User"],
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
    )

    assert freeze_file.exists()
    assert result.paths and all(path.exists() for path in result.paths)


def test_generate_fixtures_with_freeze_seeds(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "fixtures" / "{model}.py"
    freeze_file = tmp_path / "seeds.json"

    result = api_module.generate_fixtures(
        module_path,
        out=output,
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
    )

    assert freeze_file.exists()
    assert result.path is not None and result.path.exists()
    assert len(result.models) >= 2


def test_generate_schema_template_error(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    template = tmp_path / "{model}" / "schema.json"

    with pytest.raises(EmitError):
        api_module.generate_schema(module_path, out=template)


def test_generate_json_error_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    out_template = tmp_path / "out" / "{model}.json"

    monkeypatch.setattr(
        "pydantic_fixturegen.api._runtime.emit_json_samples",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(EmitError) as exc_info:
        api_module.generate_json(module_path, out=out_template, include=["models.User"])

    assert exc_info.value.details
    assert exc_info.value.details.get("base_output")


def test_generate_fixtures_error_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "fixtures" / "{model}.py"

    monkeypatch.setattr(
        "pydantic_fixturegen.api._runtime.emit_pytest_fixtures",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(EmitError) as exc_info:
        api_module.generate_fixtures(module_path, out=output, include=["models.User"])

    assert exc_info.value.details
    assert exc_info.value.details.get("base_output")


def test_generate_schema_error_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(tmp_path)
    output = tmp_path / "schema.json"

    monkeypatch.setattr(
        "pydantic_fixturegen.api._runtime.emit_model_schema",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(EmitError) as exc_info:
        api_module.generate_schema(module_path, out=output, include=["models.User"])

    assert exc_info.value.details
    assert exc_info.value.details.get("base_output")


def test_generate_api_handles_relative_imports(tmp_path: Path) -> None:
    module_path = _write_relative_import_package(tmp_path)

    json_out = tmp_path / "request.json"
    fixtures_out = tmp_path / "fixtures.py"
    schema_out = tmp_path / "schema.json"
    include = ["lib.models.example_model.ExampleRequest"]

    json_result = api_module.generate_json(
        module_path,
        out=json_out,
        include=include,
    )
    assert json_result.paths and json_result.paths[0].exists()

    fixtures_result = api_module.generate_fixtures(
        module_path,
        out=fixtures_out,
        include=include,
    )
    assert fixtures_result.path is not None and fixtures_result.path.exists()

    schema_result = api_module.generate_schema(
        module_path,
        out=schema_out,
        include=include,
    )
    assert schema_result.path is not None and schema_result.path.exists()
