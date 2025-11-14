from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path

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
