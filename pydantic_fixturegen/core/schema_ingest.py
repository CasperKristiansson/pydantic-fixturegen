"""Utilities for ingesting JSON Schema and OpenAPI documents into cached modules."""

from __future__ import annotations

import hashlib
import importlib
import json
import keyword
import re
import sys
import warnings
from collections import OrderedDict
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
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=(
                            "Core Pydantic V1 functionality isn't compatible with Python 3.14 "
                            "or greater."
                        ),
                    )
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
            if self._fallback_to_builtin_compiler(kind, input_path, output_path, exc):
                return
            raise DiscoveryError(
                f"Failed to ingest schema via datamodel-code-generator: {exc}",
                details={"path": str(input_path)},
            ) from exc

    def _fallback_to_builtin_compiler(
        self,
        kind: SchemaKind,
        input_path: Path,
        output_path: Path,
        exc: Exception,
    ) -> bool:
        message = str(exc)
        if "Core Pydantic V1 functionality isn't compatible with Python 3.14" not in message:
            return False

        try:
            document = _load_schema_document(input_path)
        except Exception as parse_exc:  # pragma: no cover - defensive
            raise DiscoveryError(
                f"Failed to load schema document for fallback compiler: {parse_exc}",
                details={"path": str(input_path)},
            ) from parse_exc

        compiler = _SimpleSchemaCompiler(document)
        try:
            if kind is SchemaKind.JSON_SCHEMA:
                compiler.compile_json_schema()
            else:
                compiler.compile_openapi_document()
        except DiscoveryError:
            raise
        except Exception as fallback_exc:  # pragma: no cover - defensive
            raise DiscoveryError(
                f"Fallback schema compiler failed: {fallback_exc}",
                details={"path": str(input_path)},
            ) from fallback_exc

        output_path.write_text(compiler.render_module(), encoding="utf-8")
        return True


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

    def _model_validate(cls: type[Any], obj: Any, /, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        return cls.parse_obj(obj)

    def _model_validate_json(cls: type[Any], data: Any, /, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
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


# --------------------------------------------------------------------------- fallback logic


def _load_schema_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    text_stripped = text.lstrip()
    if text_stripped.startswith("{") or text_stripped.startswith("["):
        return json.loads(text)
    try:  # pragma: no cover - optional yaml dependency
        import yaml
    except ModuleNotFoundError as exc:
        raise DiscoveryError(
            "YAML support is required to ingest schemas; install the 'openapi' extra.",
            details={"dependency": "pyyaml"},
        ) from exc
    return yaml.safe_load(text)


@dataclass
class _FieldSpec:
    name: str
    annotation: str
    default_expr: str


@dataclass
class _ModelSpec:
    name: str
    fields: list[_FieldSpec]


class _SimpleSchemaCompiler:
    """JSON Schema/OpenAPI compiler used when datamodel-code-generator is unavailable."""

    def __init__(self, document: Any) -> None:
        if not isinstance(document, dict):
            raise DiscoveryError("Schema documents must deserialize into mappings.")
        self.document = document
        self.models: OrderedDict[str, _ModelSpec] = OrderedDict()
        self._in_progress: set[str] = set()
        self._counter = 0
        self._imports_any = False
        self._imports_literal = False
        self._imports_datetime: set[str] = set()
        self._needs_field = False

    # ------------------------------------------------------------------ public API
    def compile_json_schema(self) -> None:
        title = self.document.get("title") or "IngestedModel"
        root_name = self._sanitize_class_name(title)
        self._compile_model(root_name, self.document)

    def compile_openapi_document(self) -> None:
        components = self.document.get("components", {})
        schemas = components.get("schemas") if isinstance(components, dict) else None
        if not isinstance(schemas, dict) or not schemas:
            raise DiscoveryError(
                "OpenAPI document does not contain any components.schemas entries."
            )
        for name, schema in schemas.items():
            if isinstance(schema, dict):
                self._compile_model(self._sanitize_class_name(name), schema)

    def render_module(self) -> str:
        lines: list[str] = ["from __future__ import annotations", ""]
        typing_imports: list[str] = []
        if self._imports_any:
            typing_imports.append("Any")
        if self._imports_literal:
            typing_imports.append("Literal")
        if typing_imports:
            lines.append(f"from typing import {', '.join(sorted(typing_imports))}")
        if self._imports_datetime:
            dt_exports = ", ".join(sorted(self._imports_datetime))
            lines.append(f"from datetime import {dt_exports}")
        lines.append("from pydantic import BaseModel" + (", Field" if self._needs_field else ""))
        lines.append("")
        lines.append("__pfg_schema_fallback__ = True")
        lines.append("")

        if not self.models:
            lines.append("class SchemaModel(BaseModel):")
            lines.append("    pass")
            return "\n".join(lines) + "\n"

        for model in self.models.values():
            lines.append(f"class {model.name}(BaseModel):")
            if not model.fields:
                lines.append("    pass")
            else:
                for field in model.fields:
                    lines.append(f"    {field.name}: {field.annotation} = {field.default_expr}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ compilation
    def _compile_model(self, name: str, schema: dict[str, Any]) -> str:
        if not isinstance(schema, dict):
            raise DiscoveryError("Invalid schema segment encountered while compiling models.")
        safe_name = self._unique_model_name(name)
        if safe_name in self.models:
            return safe_name
        if safe_name in self._in_progress:
            return safe_name
        self._in_progress.add(safe_name)

        properties = schema.get("properties")
        if properties is None:
            properties = {}
        if not isinstance(properties, dict):
            properties = {}

        required = (
            set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()
        )
        fields: list[_FieldSpec] = []
        for raw_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                field_schema = {}
            py_name = self._sanitize_identifier(raw_name)
            optional_annotation, default_expr, alias_expr = self._annotation_for_field(
                schema=field_schema,
                field_base=f"{safe_name}_{py_name}",
                required=raw_name in required,
                alias=raw_name if py_name != raw_name else None,
            )
            fields.append(
                _FieldSpec(
                    name=py_name,
                    annotation=optional_annotation,
                    default_expr=alias_expr or default_expr,
                )
            )
        self._in_progress.remove(safe_name)
        self.models[safe_name] = _ModelSpec(name=safe_name, fields=fields)
        return safe_name

    # ------------------------------------------------------------------ helpers
    def _annotation_for_field(
        self,
        *,
        schema: dict[str, Any],
        field_base: str,
        required: bool,
        alias: str | None,
    ) -> tuple[str, str, str | None]:
        annotation, nullable = self._annotation_from_schema(schema, field_base)
        default_expr = "..." if required and not nullable else "None"
        if nullable and annotation != "Any":
            annotation = f"{annotation} | None"
        rendered_default = default_expr
        if alias is not None:
            self._needs_field = True
            rendered_default = f"Field({default_expr}, alias={alias!r})"
        return annotation, default_expr, rendered_default

    def _annotation_from_schema(self, schema: dict[str, Any], field_base: str) -> tuple[str, bool]:
        if "$ref" in schema:
            target_name, target_schema = self._resolve_ref(schema["$ref"])
            resolved_name = self._compile_model(target_name, target_schema)
            return resolved_name, False

        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            values = ", ".join(repr(value) for value in schema["enum"])
            self._imports_literal = True
            return f"Literal[{values}]", False

        schema_type = schema.get("type")
        nullable = False
        if isinstance(schema_type, list):
            nullable = "null" in schema_type
            non_null_types = [entry for entry in schema_type if entry != "null"]
            schema_type = non_null_types[0] if non_null_types else None

        if schema_type == "string":
            fmt = schema.get("format")
            if fmt == "date-time":
                self._imports_datetime.add("datetime")
                return "datetime", nullable
            if fmt == "date":
                self._imports_datetime.add("date")
                return "date", nullable
            if fmt == "time":
                self._imports_datetime.add("time")
                return "time", nullable
            return "str", nullable
        if schema_type == "integer":
            return "int", nullable
        if schema_type == "number":
            return "float", nullable
        if schema_type == "boolean":
            return "bool", nullable
        if schema_type == "array":
            items = schema.get("items")
            if isinstance(items, dict):
                inner, inner_nullable = self._annotation_from_schema(items, f"{field_base}Item")
                if inner_nullable:
                    inner = f"{inner} | None"
                return f"list[{inner}]", nullable
            self._imports_any = True
            return "list[Any]", nullable
        if schema_type == "object" or "properties" in schema:
            nested_title = schema.get("title") or f"{field_base.title()}Model"
            nested_name = self._compile_model(self._sanitize_class_name(nested_title), schema)
            return nested_name, nullable

        self._imports_any = True
        return "Any", nullable

    def _resolve_ref(self, ref: str) -> tuple[str, dict[str, Any]]:
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise DiscoveryError(f"Unsupported $ref '{ref}'.")
        parts = [segment for segment in ref[2:].split("/") if segment]
        node: Any = self.document
        for segment in parts:
            node = node.get(segment) if isinstance(node, dict) else None
            if node is None:
                break
        if not isinstance(node, dict):
            raise DiscoveryError(f"Could not resolve schema reference: {ref}")
        return self._sanitize_class_name(parts[-1] if parts else "ReferencedModel"), node

    def _sanitize_class_name(self, value: str) -> str:
        cleaned = re.sub(r"\W|^(?=\d)", "_", value)
        cleaned = cleaned or "SchemaModel"
        if keyword.iskeyword(cleaned):
            cleaned += "_"
        return cleaned

    def _sanitize_identifier(self, value: str) -> str:
        cleaned = re.sub(r"\W|^(?=\d)", "_", value)
        cleaned = cleaned or "field"
        if keyword.iskeyword(cleaned):
            cleaned += "_"
        return cleaned

    def _unique_model_name(self, candidate: str) -> str:
        base = candidate
        index = 1
        while candidate in self.models or candidate in self._in_progress:
            candidate = f"{base}{index}"
            index += 1
        return candidate
