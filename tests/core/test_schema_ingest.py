from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest

from pydantic_fixturegen.core import schema_ingest


@contextmanager
def _noop_context():
    yield


class _DummyDCG:
    class InputFileType:
        OpenAPI = object()
        JsonSchema = object()

    class DataModelType:
        PydanticV2BaseModel = object()

    class PythonVersion:
        PY_310 = object()

    __version__ = "1.2.3"

    @staticmethod
    def generate(**kwargs):
        output = Path(kwargs["output"])
        output.write_text("# generated via DCG\nclass Example:\n    pass\n", encoding="utf-8")


def _patch_dcg(monkeypatch: pytest.MonkeyPatch, dcg_obj: object) -> None:
    def fake_import(name: str):
        if name == "datamodel_code_generator":
            return dcg_obj
        return importlib.import_module(name)

    monkeypatch.setattr(schema_ingest, "_ensure_pydantic_compatibility", _noop_context)
    monkeypatch.setattr(schema_ingest.importlib, "import_module", fake_import)


def test_schema_ingester_invokes_datamodel_code_generator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dcg(monkeypatch, _DummyDCG)
    schema_ingest._DCG_VERSION = _DummyDCG.__version__
    ingester = schema_ingest.SchemaIngester(root=tmp_path)
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"title": "Example"}', encoding="utf-8")

    module = ingester.ingest_json_schema(schema_file)
    assert module.path.exists()
    content = module.path.read_text(encoding="utf-8")
    assert "generated via DCG" in content

    # Second ingest should reuse cached module without regenerating
    cached = ingester.ingest_json_schema(schema_file)
    assert cached.path == module.path


class _FailingDCG(_DummyDCG):
    @staticmethod
    def generate(**kwargs):
        raise RuntimeError("Core Pydantic V1 functionality isn't compatible with Python 3.14")


def test_schema_ingester_fallback_compiler(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dcg(monkeypatch, _FailingDCG)
    schema_ingest._DCG_VERSION = _FailingDCG.__version__
    ingester = schema_ingest.SchemaIngester(root=tmp_path)
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"title": "FallbackModel", "type": "object"}', encoding="utf-8")

    module = ingester.ingest_json_schema(schema_file)
    text = module.path.read_text(encoding="utf-8")
    assert "class FallbackModel" in text


def test_schema_ingester_ingest_openapi_writes_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dcg(monkeypatch, _DummyDCG)
    schema_ingest._DCG_VERSION = _DummyDCG.__version__
    ingester = schema_ingest.SchemaIngester(root=tmp_path)
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text("openapi: 3.1.0", encoding="utf-8")

    payload = b"openapi: 3.1.0\ncomponents: {}\n"
    module = ingester.ingest_openapi(
        spec_path,
        document_bytes=payload,
        fingerprint="filtered",
    )
    assert module.path.exists()

    sources_dir = tmp_path / ".pfg-cache" / "schemas" / "sources"
    stored = list(sources_dir.glob("*.yaml"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == payload


def test_schema_ingester_fallback_only_on_known_error(tmp_path: Path) -> None:
    ingester = schema_ingest.SchemaIngester(root=tmp_path)
    schema_file = tmp_path / "minimal.json"
    schema_file.write_text("{}", encoding="utf-8")
    output_file = tmp_path / "dummy.py"

    assert not ingester._fallback_to_builtin_compiler(  # type: ignore[attr-defined]
        schema_ingest.SchemaKind.JSON_SCHEMA,
        schema_file,
        output_file,
        RuntimeError("boom"),
    )


def test_ensure_pydantic_compatibility_shims_base_model(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyBaseModel:
        __pfg_v2_shim__ = False

        def __init__(self, value: str = "value") -> None:
            self.value = value

        @classmethod
        def parse_obj(cls, obj: object) -> dict[str, object]:
            return {"parsed": obj}

        @classmethod
        def parse_raw(cls, raw: str) -> dict[str, object]:
            return {"raw": raw}

        def dict(self, **kwargs: object) -> dict[str, str]:
            return {"value": self.value}

        def json(self, **kwargs: object) -> str:
            return json.dumps(self.dict())

    fake_pydantic = ModuleType("pydantic")
    fake_pydantic.__version__ = "2.0.0"
    fake_pydantic.BaseModel = DummyBaseModel  # type: ignore[attr-defined]
    fake_v1 = ModuleType("pydantic.v1")
    fake_v1.BaseModel = DummyBaseModel  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "pydantic", fake_pydantic)
    monkeypatch.setitem(sys.modules, "pydantic.v1", fake_v1)
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "pydantic.v1":
            return fake_v1
        return real_import_module(name, package)

    monkeypatch.setattr(schema_ingest.importlib, "import_module", fake_import_module)

    with schema_ingest._ensure_pydantic_compatibility():
        compat_module = sys.modules["pydantic"]
        assert compat_module is fake_v1
        instance = compat_module.BaseModel("abc")  # type: ignore[attr-defined]
        assert instance.model_dump() == {"value": "abc"}
        dumped = json.loads(instance.model_dump_json())
        assert dumped == {"value": "abc"}
        assert instance.model_validate({"value": "from-validate"}) == {"parsed": {"value": "from-validate"}}
        assert instance.model_validate_json("null") == {"raw": "null"}

    assert sys.modules["pydantic"] is fake_pydantic
    assert getattr(fake_v1.BaseModel, "__pfg_v2_shim__") is True  # type: ignore[attr-defined]


def test_load_schema_document_reads_json(tmp_path: Path) -> None:
    doc_path = tmp_path / "doc.json"
    doc_path.write_text('[{"value": 1}]', encoding="utf-8")
    assert schema_ingest._load_schema_document(doc_path) == [{"value": 1}]


def test_load_schema_document_reads_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doc_path = tmp_path / "doc.yaml"
    doc_path.write_text("key: value\n", encoding="utf-8")

    yaml_module = ModuleType("yaml")
    yaml_module.safe_load = lambda text: {"loaded": text.strip()}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yaml", yaml_module)

    assert schema_ingest._load_schema_document(doc_path) == {"loaded": "key: value"}


def test_simple_schema_compiler_renders_complex_models() -> None:
    document = {
        "title": "Root Example",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "alias-field": {"type": "integer"},
            "nick": {"type": ["string", "null"]},
            "status": {"enum": ["draft", "done"]},
            "event_time": {"type": "string", "format": "date-time"},
            "holiday": {"type": "string", "format": "date"},
            "clock": {"type": "string", "format": "time"},
            "numbers": {"type": "array", "items": {"type": ["integer", "null"]}},
            "payloads": {"type": "array"},
            "config": {"type": "object", "properties": {"flag": {"type": "boolean"}}},
            "extra": {},
            "ref": {"$ref": "#/$defs/Nested Model"},
            "class": {"type": "integer"},
        },
        "required": ["name", "alias-field", "ref"],
        "$defs": {
            "Nested Model": {
                "type": "object",
                "properties": {
                    "values": {"type": ["number", "null"]},
                },
            }
        },
    }

    compiler = schema_ingest._SimpleSchemaCompiler(document)
    compiler.compile_json_schema()
    rendered = compiler.render_module()

    assert "from typing import Any, Literal" in rendered
    assert "from datetime import date, datetime, time" in rendered
    assert "alias_field: int = Field(..., alias='alias-field')" in rendered
    assert "nick: str | None = None" in rendered
    assert "status: Literal['draft', 'done']" in rendered
    assert "numbers: list[int | None]" in rendered
    assert "payloads: list[Any]" in rendered
    assert "extra: Any = None" in rendered
    assert "class_: int = Field(None, alias='class')" in rendered
    assert "class NestedModel" in rendered or "class Nested_Model" in rendered
    assert "__pfg_schema_fallback__ = True" in rendered


def test_simple_schema_compiler_render_without_models() -> None:
    compiler = schema_ingest._SimpleSchemaCompiler({})
    module_text = compiler.render_module()
    assert "class SchemaModel(BaseModel)" in module_text


def test_simple_schema_compiler_openapi_validation() -> None:
    compiler = schema_ingest._SimpleSchemaCompiler({"components": {"schemas": {}}})
    with pytest.raises(schema_ingest.DiscoveryError):
        compiler.compile_openapi_document()


def test_simple_schema_compiler_openapi_models() -> None:
    document = {
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                },
                "Another Model": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            }
        }
    }
    compiler = schema_ingest._SimpleSchemaCompiler(document)
    compiler.compile_openapi_document()
    rendered = compiler.render_module()
    assert "class User(BaseModel)" in rendered
    assert "class Another_Model(BaseModel)" in rendered


def test_simple_schema_compiler_invalid_document() -> None:
    with pytest.raises(schema_ingest.DiscoveryError):
        schema_ingest._SimpleSchemaCompiler(["not-a-mapping"])  # type: ignore[arg-type]


def test_simple_schema_compiler_resolve_ref_failure() -> None:
    compiler = schema_ingest._SimpleSchemaCompiler({"title": "Doc"})
    with pytest.raises(schema_ingest.DiscoveryError):
        compiler._resolve_ref("#/missing/path")
