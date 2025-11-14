"""Utilities for rendering templated output paths."""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

from .errors import EmitError

__all__ = [
    "OutputTemplate",
    "OutputTemplateContext",
    "OutputTemplateError",
    "sanitize_path_segment",
]


_ALLOWED_FIELDS = {"model", "case_index", "timestamp"}
_PLACEHOLDER_PATTERN = re.compile(r"{([^{}]+)}")
_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class OutputTemplateError(EmitError):
    """Raised when a templated path cannot be rendered safely."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message, details=details)


@dataclass(slots=True)
class OutputTemplateContext:
    """Context data supplied when rendering an :class:`OutputTemplate`."""

    model: str | None = None
    timestamp: _dt.datetime | None = None


class _StrictFormatter(Formatter):
    def get_value(self, key: object, args: Sequence[Any], kwargs: Mapping[str, Any]) -> object:
        if isinstance(key, str):
            try:
                return kwargs[key]
            except KeyError as exc:
                raise OutputTemplateError(
                    f"Missing template variable '{{{key}}}'.",
                    details={"field": key},
                ) from exc
        raise OutputTemplateError("Positional fields are not supported in templates.")


class _TemplateTimestamp:
    def __init__(self, value: _dt.datetime) -> None:
        self._value = value

    def __format__(self, format_spec: str) -> str:
        if format_spec:
            rendered = self._value.strftime(format_spec)
        else:
            rendered = self._value.strftime("%Y%m%dT%H%M%S")
        sanitized = _sanitize_segment(rendered)
        return sanitized or "timestamp"

    def __str__(self) -> str:
        return self.__format__("")


class _TemplateString(str):
    def __new__(cls, value: str) -> _TemplateString:
        sanitized = _sanitize_segment(value)
        return str.__new__(cls, sanitized or "artifact")


class _TemplateCaseIndex(int):
    def __new__(cls, value: int) -> _TemplateCaseIndex:
        if value < 1:
            raise OutputTemplateError(
                "case_index must be >= 1",
                details={"case_index": value},
            )
        return int.__new__(cls, value)

    def __format__(self, format_spec: str) -> str:
        formatted = format(int(self), format_spec) if format_spec else str(int(self))
        return _sanitize_segment(formatted) or "1"

    def __str__(self) -> str:
        return self.__format__("")


def _sanitize_segment(value: str) -> str:
    sanitized = _SANITIZE_PATTERN.sub("_", value.strip())
    return sanitized.strip("._-")


def sanitize_path_segment(value: str) -> str:
    """Public helper that mirrors the sanitisation used by output templates."""

    return _sanitize_segment(value)


def _collect_fields(template: str) -> set[str]:
    return {match.group(1) for match in _PLACEHOLDER_PATTERN.finditer(template)}


def _contains_placeholder(segment: str) -> bool:
    return bool(_PLACEHOLDER_PATTERN.search(segment))


class OutputTemplate:
    """Render filesystem paths from user-supplied templates."""

    def __init__(self, template: str | Path) -> None:
        self._raw = str(template)
        self._formatter = _StrictFormatter()
        self._fields = _collect_fields(self._raw)
        invalid = self._fields - _ALLOWED_FIELDS
        if invalid:
            raise OutputTemplateError(
                "Unsupported template variable",
                details={"fields": sorted(invalid)},
            )

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def fields(self) -> set[str]:
        return set(self._fields)

    def uses_case_index(self) -> bool:
        return "case_index" in self._fields

    def has_dynamic_directories(self) -> bool:
        candidate = Path(self._raw)
        return any(_contains_placeholder(segment) for segment in candidate.parts[:-1])

    def watch_parent(self) -> Path:
        candidate = Path(self._raw)
        parts = list(candidate.parts)
        if len(parts) <= 1:
            return Path(".")

        stable: list[str] = []
        for part in parts[:-1]:
            if _contains_placeholder(part):
                break
            stable.append(part)

        if not stable:
            return Path(".")
        return Path(*stable)

    def preview_path(self) -> Path:
        context = OutputTemplateContext(model="preview")
        case_index = 1 if self.uses_case_index() else None
        return self.render(context=context, case_index=case_index)

    def render(
        self,
        *,
        context: OutputTemplateContext | None = None,
        case_index: int | None = None,
    ) -> Path:
        if not self._fields:
            return Path(self._raw).expanduser()

        ctx = context or OutputTemplateContext()
        values: dict[str, object] = {}
        if "model" in self._fields:
            if ctx.model is None:
                raise OutputTemplateError(
                    "Template variable '{model}' requires a model context.",
                )
            values["model"] = _TemplateString(ctx.model)
        if "timestamp" in self._fields:
            timestamp = ctx.timestamp or _dt.datetime.now(_dt.timezone.utc)
            values["timestamp"] = _TemplateTimestamp(timestamp)
        if "case_index" in self._fields:
            if case_index is None:
                raise OutputTemplateError(
                    "Template variable '{case_index}' requires an index.",
                )
            values["case_index"] = _TemplateCaseIndex(case_index)

        rendered = self._formatter.format(self._raw, **values).strip()
        if not rendered:
            raise OutputTemplateError(
                "Rendered template produced an empty path.",
                details={"template": self._raw},
            )

        path = Path(rendered).expanduser()
        if any(part == ".." for part in path.parts):
            base = Path.cwd()
            path = (base / path).resolve()
        return path
