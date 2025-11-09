from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.schema_ingest import (
    SchemaIngester,
    SchemaKind,
    _ensure_pydantic_compatibility,
    _patch_pydantic_v1_for_v2_api,
)


def test_ingest_json_schema_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schema_file = tmp_path / "schema.json"
    schema_file.write_text("{}", encoding="utf-8")

    calls: list[tuple[SchemaKind, Path, Path]] = []

    def fake_generate(self, *, kind, input_path, output_path):
        calls.append((kind, input_path, output_path))
        output_path.write_text("# generated", encoding="utf-8")

    monkeypatch.setattr(SchemaIngester, "_generate_models", fake_generate)

    ingester = SchemaIngester(root=tmp_path)
    first = ingester.ingest_json_schema(schema_file)
    assert first.path.exists()

    # second call should reuse cached module without invoking generator again
    second = ingester.ingest_json_schema(schema_file)
    assert first.path == second.path
    assert len(calls) == 1


def test_ingest_openapi_writes_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.1.0", encoding="utf-8")

    def fake_generate(self, *, kind, input_path, output_path):
        output_path.write_text("# generated", encoding="utf-8")
        assert kind is SchemaKind.OPENAPI
        assert input_path.suffix == ".yaml"

    monkeypatch.setattr(SchemaIngester, "_generate_models", fake_generate)

    payload = {"openapi": "3.1.0"}
    ingester = SchemaIngester(root=tmp_path)
    module = ingester.ingest_openapi(
        spec,
        document_bytes=json.dumps(payload).encode("utf-8"),
        fingerprint="demo",
    )

    assert module.path.exists()


def test_ingest_json_schema_propagates_discovery_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_file = tmp_path / "schema.json"
    schema_file.write_text("{}", encoding="utf-8")

    def fail_generate(self, **kwargs):
        raise DiscoveryError("boom")  # noqa: ARG001

    monkeypatch.setattr(SchemaIngester, "_generate_models", fail_generate)

    ingester = SchemaIngester(root=tmp_path)
    with pytest.raises(DiscoveryError, match="boom"):
        ingester.ingest_json_schema(schema_file)


def test_generate_models_invokes_dcg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    records: dict[str, object] = {}

    @contextmanager
    def fake_compat():
        yield

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest._ensure_pydantic_compatibility", fake_compat
    )

    class FakeDCG:
        __version__ = "1.0.0"

        class InputFileType:
            OpenAPI = "openapi"
            JsonSchema = "json"

        class DataModelType:
            PydanticV2BaseModel = "BaseModel"

        class PythonVersion:
            PY_310 = "3.10"

        def generate(self, **kwargs):
            records.update(kwargs)
            kwargs["output"].write_text("# stub", encoding="utf-8")

    def fake_import(name: str):
        if name == "datamodel_code_generator":
            return FakeDCG()
        return real_import_module(name)

    real_import_module = importlib.import_module
    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest.importlib.import_module", fake_import
    )

    ingester = SchemaIngester(root=tmp_path)
    input_schema = tmp_path / "schema.json"
    input_schema.write_text("{}", encoding="utf-8")
    output_module = tmp_path / "out.py"

    ingester._generate_models(
        kind=SchemaKind.JSON_SCHEMA,
        input_path=input_schema,
        output_path=output_module,
    )

    assert output_module.exists()
    assert records["input_file_type"] == FakeDCG.InputFileType.JsonSchema


def test_generate_models_missing_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def fake_compat():
        yield

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest._ensure_pydantic_compatibility", fake_compat
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest.importlib.import_module",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
    )

    ingester = SchemaIngester(root=tmp_path)
    with pytest.raises(DiscoveryError, match="datamodel-code-generator"):
        ingester._generate_models(
            kind=SchemaKind.JSON_SCHEMA,
            input_path=tmp_path / "schema.json",
            output_path=tmp_path / "out.py",
        )


def test_ingest_json_schema_uses_fallback_compiler(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_doc = {
        "title": "User",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema_doc), encoding="utf-8")

    def fake_import(name: str):
        if name == "datamodel_code_generator":
            raise RuntimeError(
                "Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater."
            )
        return real_import_module(name)

    real_import_module = importlib.import_module
    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest.importlib.import_module",
        fake_import,
    )

    @contextmanager
    def fake_compat():
        yield

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest._ensure_pydantic_compatibility",
        fake_compat,
    )

    ingester = SchemaIngester(root=tmp_path)
    module = ingester.ingest_json_schema(schema_path)
    contents = module.path.read_text(encoding="utf-8")
    assert "class User(BaseModel):" in contents
    assert "name: str" in contents
    assert "age: int" in contents
    loaded = _import_module_from_path(module.path)
    from pydantic import BaseModel

    assert getattr(loaded, "__pfg_schema_fallback__", False) is True
    assert issubclass(loaded.User, BaseModel)


def test_ingest_openapi_fallback_generates_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Widget": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                }
            }
        },
    }

    spec_path = tmp_path / "spec.json"
    spec_path.write_text("{}", encoding="utf-8")
    payload = json.dumps(document).encode("utf-8")

    def fake_import(name: str):
        if name == "datamodel_code_generator":
            raise RuntimeError(
                "Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater."
            )
        return real_import_module(name)

    real_import_module = importlib.import_module
    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest.importlib.import_module",
        fake_import,
    )

    @contextmanager
    def fake_compat():
        yield

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest._ensure_pydantic_compatibility",
        fake_compat,
    )

    ingester = SchemaIngester(root=tmp_path)
    module = ingester.ingest_openapi(spec_path, document_bytes=payload, fingerprint="demo")
    contents = module.path.read_text(encoding="utf-8")
    assert "class Widget(BaseModel):" in contents
    assert "label: str" in contents
    loaded = _import_module_from_path(module.path)
    from pydantic import BaseModel

    assert getattr(loaded, "__pfg_schema_fallback__", False) is True
    assert issubclass(loaded.Widget, BaseModel)


def test_generate_models_rethrows_discovery_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    @contextmanager
    def failing_context():
        raise DiscoveryError("compat failure")
        yield

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest._ensure_pydantic_compatibility",
        failing_context,
    )

    ingester = SchemaIngester(root=tmp_path)
    input_schema = tmp_path / "schema.json"
    input_schema.write_text("{}", encoding="utf-8")
    output_module = tmp_path / "out.py"

    with pytest.raises(DiscoveryError, match="compat failure"):
        ingester._generate_models(
            kind=SchemaKind.JSON_SCHEMA,
            input_path=input_schema,
            output_path=output_module,
        )


def test_ensure_pydantic_compatibility_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "pydantic" or name.startswith("pydantic."):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with (
        pytest.raises(DiscoveryError, match="Pydantic is required"),
        _ensure_pydantic_compatibility(),
    ):
        pass


def test_ensure_pydantic_compatibility_v1_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    fake_module = SimpleNamespace(__version__="1.10.0")
    real_import = builtins.__import__
    seen: dict[str, object] = {}

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pydantic":
            seen["module"] = fake_module
            return fake_module
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    sys.modules.pop("pydantic", None)
    with _ensure_pydantic_compatibility():
        assert seen["module"] is fake_module
        assert "pydantic" not in sys.modules


def test_ensure_pydantic_compatibility_uses_v1_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    shim = SimpleNamespace()
    base_model = type("BaseModel", (), {})
    shim.BaseModel = base_model
    shim.__dict__["__pfg_v2_shim__"] = False

    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "pydantic":
            return SimpleNamespace(__version__="2.5.0")
        if name == "pydantic.v1":
            return shim
        return real_import(name, package=package)

    monkeypatch.setattr(
        "pydantic_fixturegen.core.schema_ingest.importlib.import_module",
        fake_import,
    )

    with _ensure_pydantic_compatibility():
        assert sys.modules["pydantic"] is shim
        assert hasattr(base_model, "model_dump_json")


def test_patch_pydantic_v1_for_v2_api_adds_methods() -> None:
    class DummyModel:
        called = {}

        @classmethod
        def parse_obj(cls, data):
            cls.called["obj"] = data
            return data

        @classmethod
        def parse_raw(cls, data):
            cls.called["raw"] = data
            return data

        def dict(self, *args, **kwargs):
            return {"value": 1}

        def json(self, *args, **kwargs):
            return json.dumps(self.dict())

    module = SimpleNamespace(BaseModel=DummyModel)
    _patch_pydantic_v1_for_v2_api(module)

    DummyModel.model_validate({"x": 1})
    DummyModel.model_validate_json("{}")
    instance = DummyModel()
    assert instance.model_dump(mode="python") == {"value": 1}
    assert instance.model_dump(mode="json") == {"value": 1}
    instance.model_dump_json()
    assert DummyModel.called["obj"] == {"x": 1}


def test_patch_pydantic_v1_for_v2_api_is_idempotent() -> None:
    class DummyModel:
        __pfg_v2_shim__ = True

    module = SimpleNamespace(BaseModel=DummyModel)
    _patch_pydantic_v1_for_v2_api(module)


def _import_module_from_path(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"schema_fallback_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module
