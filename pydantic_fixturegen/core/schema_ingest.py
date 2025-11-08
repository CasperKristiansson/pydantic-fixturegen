"""Utilities for ingesting JSON Schema and OpenAPI documents into cached modules."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from .errors import DiscoveryError

_DCG_VERSION = "unavailable"


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
        try:
            with _ensure_pydantic_compatibility():
                sys.modules.pop("datamodel_code_generator", None)
                dcg = importlib.import_module("datamodel_code_generator")
                file_type = (
                    dcg.InputFileType.OpenAPI
                    if kind is SchemaKind.OPENAPI
                    else dcg.InputFileType.JsonSchema
                )
                global _DCG_VERSION
                _DCG_VERSION = getattr(dcg, "__version__", "unknown")
                self._dcg_version = _DCG_VERSION
                dcg.generate(
                    input_=input_path,
                    input_file_type=file_type,
                    output=output_path,
                    output_model_type=dcg.DataModelType.PydanticV2BaseModel,
                    target_python_version=dcg.PythonVersion.PY_310,
                    disable_timestamp=True,
                    reuse_model=True,
                    disable_future_imports=True,
                )
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency error
            missing = getattr(exc, "name", "dependency")
            raise DiscoveryError(
                "Schema ingestion requires `datamodel-code-generator`. "
                "Install the `openapi` extra via `pip install pydantic-fixturegen[openapi]`.",
                details={"path": str(input_path), "dependency": missing},
            ) from exc
        except DiscoveryError:
            raise
        except Exception as exc:  # pragma: no cover - error path
            raise DiscoveryError(
                f"Failed to ingest schema via datamodel-code-generator: {exc}",
                details={"path": str(input_path)},
            ) from exc


@contextmanager
def _ensure_pydantic_compatibility() -> Iterator[None]:
    """Temporarily expose Pydantic v1 API for datamodel-code-generator."""

    try:
        import pydantic as pydantic_module
    except ModuleNotFoundError as exc:  # pragma: no cover - packaging issue
        raise DiscoveryError(
            "Pydantic is required for schema ingestion workflows.",
            details={"dependency": "pydantic"},
        ) from exc

    if getattr(pydantic_module, "__version__", "").startswith("1."):
        yield
        return

    saved: dict[str, Any] = {}
    for name, module in list(sys.modules.items()):
        if name == "pydantic" or name.startswith("pydantic."):
            saved[name] = module
            sys.modules.pop(name, None)

    try:
        compat_module = importlib.import_module("pydantic.v1")
    except ModuleNotFoundError as exc:  # pragma: no cover - mis-installed pydantic
        raise DiscoveryError(
            "Pydantic v1 compatibility module is unavailable; upgrade to `pydantic>=2`.",
            details={"dependency": "pydantic.v1"},
        ) from exc

    _patch_pydantic_v1_for_v2_api(compat_module)
    sys.modules["pydantic"] = compat_module
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == "pydantic" or name.startswith("pydantic."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def _patch_pydantic_v1_for_v2_api(module: Any) -> None:
    """Augment the v1 compatibility module with Pydantic v2-esque helpers."""

    base_model = getattr(module, "BaseModel", None)
    if base_model is None or getattr(base_model, "__pfg_v2_shim__", False):
        return

    def _model_validate(cls: type[Any], obj: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        return cls.parse_obj(obj)

    def _model_validate_json(cls: type[Any], data: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        return cls.parse_raw(data)

    def _model_dump(
        self: Any,
        *,
        mode: str = "python",
        include: Any = None,
        exclude: Any = None,
        context: Any = None,  # noqa: ARG001 - parity with v2 signature
        by_alias: bool | None = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        exclude_computed_fields: bool = False,  # noqa: ARG001
        round_trip: bool = False,  # noqa: ARG001
        warnings: Any = True,  # noqa: ARG001
        fallback: Any = None,  # noqa: ARG001
        serialize_as_any: bool = False,  # noqa: ARG001
    ) -> Any:
        if mode == "json":
            return json.loads(
                self.json(
                    include=include,
                    exclude=exclude,
                    by_alias=bool(by_alias) if by_alias is not None else False,
                    exclude_unset=exclude_unset,
                    exclude_defaults=exclude_defaults,
                    exclude_none=exclude_none,
                )
            )
        return self.dict(
            include=include,
            exclude=exclude,
            by_alias=bool(by_alias) if by_alias is not None else False,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def _model_dump_json(
        self: Any,
        *,
        indent: int | None = None,
        include: Any = None,
        exclude: Any = None,
        context: Any = None,  # noqa: ARG001
        by_alias: bool | None = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        exclude_computed_fields: bool = False,  # noqa: ARG001
        round_trip: bool = False,  # noqa: ARG001
        warnings: Any = True,  # noqa: ARG001
        fallback: Any = None,  # noqa: ARG001
        serialize_as_any: bool = False,  # noqa: ARG001
    ) -> str:
        return cast(
            str,
            self.json(
                indent=indent,
                include=include,
                exclude=exclude,
                by_alias=bool(by_alias) if by_alias is not None else False,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            ),
        )

    base_model.model_validate = classmethod(_model_validate)
    base_model.model_validate_json = classmethod(_model_validate_json)
    base_model.model_dump = _model_dump
    base_model.model_dump_json = _model_dump_json
    base_model.__pfg_v2_shim__ = True


__all__ = ["SchemaIngester", "SchemaKind", "SchemaModule"]
