"""Utilities for ingesting JSON Schema and OpenAPI documents into cached modules."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import DiscoveryError

DataModelType: Any
InputFileType: Any
PythonVersion: Any
generate: Any
_dcg: Any

try:  # pragma: no cover - optional import
    import datamodel_code_generator as _dcg
except ImportError:  # pragma: no cover - exercised in environments without the extra
    _dcg = None
    DataModelType = InputFileType = PythonVersion = None
    generate = None
    _DCG_VERSION = "unavailable"
else:  # pragma: no cover - import side-effects exercised in tests
    DataModelType = _dcg.DataModelType
    InputFileType = _dcg.InputFileType
    PythonVersion = _dcg.PythonVersion
    generate = _dcg.generate
    _DCG_VERSION = getattr(_dcg, "__version__", "unknown")


CACHE_ROOT = ".pfg-cache"
SCHEMA_CACHE_DIR = "schemas"
SCHEMA_MODULE_DIR = "modules"
SCHEMA_SOURCE_DIR = "sources"


class SchemaKind(str, Enum):
    """Supported schema document types."""

    JSON_SCHEMA = "json_schema"
    OPENAPI = "openapi"


@dataclass(slots=True)
class SchemaModule:
    """Details about an ingested module that can be imported later."""

    path: Path
    cache_key: str


class SchemaIngester:
    """Convert schema documents into Python modules via datamodel-code-generator."""

    def __init__(self, *, root: Path | None = None) -> None:
        base = (root or Path.cwd()) / CACHE_ROOT / SCHEMA_CACHE_DIR
        self._modules_dir = base / SCHEMA_MODULE_DIR
        self._sources_dir = base / SCHEMA_SOURCE_DIR
        self._modules_dir.mkdir(parents=True, exist_ok=True)
        self._sources_dir.mkdir(parents=True, exist_ok=True)
        self._dcg_version = _DCG_VERSION

    def ingest_json_schema(self, schema_path: Path) -> SchemaModule:
        """Materialise a JSON Schema document as a cached module."""

        payload = schema_path.read_bytes()
        return self._ensure_module(
            kind=SchemaKind.JSON_SCHEMA,
            source_path=schema_path,
            payload=payload,
            content_override=None,
            options=("json",),
        )

    def ingest_openapi(
        self,
        spec_path: Path,
        *,
        document_bytes: bytes,
        fingerprint: str,
    ) -> SchemaModule:
        """Materialise an OpenAPI document (potentially filtered) as a module."""

        return self._ensure_module(
            kind=SchemaKind.OPENAPI,
            source_path=spec_path,
            payload=document_bytes,
            content_override=document_bytes,
            options=("openapi", fingerprint),
        )

    # --------------------------------------------------------------------- internals
    def _ensure_module(
        self,
        *,
        kind: SchemaKind,
        source_path: Path,
        payload: bytes,
        content_override: bytes | None,
        options: Iterable[str],
    ) -> SchemaModule:
        cache_key = self._derive_cache_key(kind=kind, payload=payload, options=options)
        module_path = self._modules_dir / f"{cache_key}.py"
        if module_path.exists():
            return SchemaModule(path=module_path, cache_key=cache_key)

        input_path: Path
        if content_override is None:
            input_path = source_path
        else:
            suffix = source_path.suffix or ".yaml"
            spec_path = self._sources_dir / f"{cache_key}{suffix}"
            spec_path.write_bytes(content_override)
            input_path = spec_path

        self._generate_models(kind=kind, input_path=input_path, output_path=module_path)
        return SchemaModule(path=module_path, cache_key=cache_key)

    def _derive_cache_key(
        self,
        *,
        kind: SchemaKind,
        payload: bytes,
        options: Iterable[str],
    ) -> str:
        digest = hashlib.sha256()
        digest.update(kind.value.encode("utf-8"))
        digest.update(payload)
        digest.update(self._dcg_version.encode("utf-8"))
        for entry in options:
            digest.update(entry.encode("utf-8"))
        return digest.hexdigest()

    def _generate_models(self, *, kind: SchemaKind, input_path: Path, output_path: Path) -> None:
        if (
            generate is None
            or DataModelType is None
            or InputFileType is None
            or PythonVersion is None
        ):
            raise DiscoveryError(
                (
                    "Schema ingestion requires 'datamodel-code-generator'. Install the "
                    "'openapi' extra (pip install pydantic-fixturegen[openapi]) to "
                    "enable this feature."
                ),
            )

        file_type = (
            InputFileType.OpenAPI if kind is SchemaKind.OPENAPI else InputFileType.JsonSchema
        )
        try:
            generate(
                input_=input_path,
                input_file_type=file_type,
                output=output_path,
                output_model_type=DataModelType.PydanticBaseModel,
                target_python_version=PythonVersion.PY_310,
                disable_timestamp=True,
                reuse_model=True,
                disable_future_imports=True,
            )
        except Exception as exc:  # pragma: no cover - error path
            raise DiscoveryError(
                f"Failed to ingest schema via datamodel-code-generator: {exc}",
                details={"path": str(input_path)},
            ) from exc


__all__ = ["SchemaIngester", "SchemaKind", "SchemaModule"]
