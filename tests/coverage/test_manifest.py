from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core.errors import EmitError
from pydantic_fixturegen.coverage.manifest import (
    CoverageManifest,
    _prepare_manifest_target,
    build_coverage_manifest,
    compare_manifests,
)


def _write_model(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Sample(BaseModel):
    id: int
    name: str
""",
        encoding="utf-8",
    )
    return module_path


def test_build_coverage_manifest_contains_model(tmp_path: Path) -> None:
    module_path = _write_model(tmp_path)
    manifest = build_coverage_manifest(
        target=module_path,
        include=None,
        exclude=None,
        schema=None,
        openapi=None,
        routes=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=2.0,
        memory_limit_mb=128,
    )
    payload = manifest.to_payload()
    assert payload["models"]
    sample = payload["models"][0]
    assert sample["name"].endswith("Sample")
    assert sample["coverage"]["total"] == 2


def test_compare_manifests_detects_diff(tmp_path: Path) -> None:
    module_path = _write_model(tmp_path)
    manifest = build_coverage_manifest(
        target=module_path,
        include=None,
        exclude=None,
        schema=None,
        openapi=None,
        routes=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=2.0,
        memory_limit_mb=128,
    )
    payload = manifest.to_payload()
    modified = CoverageManifest.from_payload(json.loads(json.dumps(payload)))
    modified.models[0]["coverage"]["covered"] = 0
    matches, diff = compare_manifests(manifest, modified)
    assert not matches
    assert "lockfile" in diff or diff


def test_manifest_from_payload_version_mismatch() -> None:
    with pytest.raises(EmitError):
        CoverageManifest.from_payload({"version": 99})


def test_compare_manifests_equality(tmp_path: Path) -> None:
    module_path = _write_model(tmp_path)
    manifest = build_coverage_manifest(
        target=module_path,
        include=None,
        exclude=None,
        schema=None,
        openapi=None,
        routes=None,
        ast_mode=False,
        hybrid_mode=False,
        timeout=2.0,
        memory_limit_mb=128,
    )
    matches, diff = compare_manifests(manifest, manifest)
    assert matches
    assert diff == ""


def test_prepare_manifest_target_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Locked",
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.coverage.manifest.SchemaIngester.ingest_json_schema",
        lambda self, _: SimpleNamespace(path=schema_path),
    )
    module_path, includes = _prepare_manifest_target(
        target=tmp_path / "module.py",
        schema=schema_path,
        openapi=None,
        routes=None,
    )
    assert module_path.exists()
    assert includes == []


def test_prepare_manifest_target_openapi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    openapi_path = tmp_path / "spec.json"
    openapi_path.write_text("{}", encoding="utf-8")

    class DummySelection:
        def __init__(self) -> None:
            self.document = {}
            self.schemas = ["Item"]

        def fingerprint(self) -> str:
            return "fp"

    monkeypatch.setattr(
        "pydantic_fixturegen.coverage.manifest.load_openapi_document",
        lambda path: {"paths": {}},
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.coverage.manifest.select_openapi_schemas",
        lambda *args, **kwargs: DummySelection(),
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.coverage.manifest.SchemaIngester.ingest_openapi",
        lambda self, *args, **kwargs: SimpleNamespace(path=openapi_path),
    )
    monkeypatch.setattr(
        "pydantic_fixturegen.coverage.manifest.dump_document",
        lambda document: b"{}",
    )
    module_path, includes = _prepare_manifest_target(
        target=tmp_path / "module.py",
        schema=None,
        openapi=openapi_path,
        routes=["GET /items"],
    )
    assert module_path.exists()
    assert includes == ["*.Item"]


def test_prepare_manifest_target_conflict(tmp_path: Path) -> None:
    dummy = tmp_path / "dummy.json"
    dummy.write_text("{}", encoding="utf-8")
    with pytest.raises(EmitError):
        _prepare_manifest_target(
            target=tmp_path / "module.py",
            schema=dummy,
            openapi=dummy,
            routes=None,
        )
