"""Core error taxonomy and helpers for structured reporting."""

from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    """Stable error codes used across the CLI."""

    DISCOVERY = 10
    MAPPING = 20
    EMIT = 30
    UNSAFE_IMPORT = 40
    DIFF = 50
    WATCH = 60


class PFGError(Exception):
    """Base class for structured errors with stable codes."""

    code: ErrorCode
    kind: str
    details: dict[str, Any]
    hint: str | None

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode,
        kind: str,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.kind = kind
        self.details = dict(details or {})
        self.hint = hint

    def to_payload(self) -> dict[str, Any]:
        """Return a serialisable payload for JSON output."""
        return {
            "code": int(self.code),
            "kind": self.kind,
            "message": str(self),
            "details": self.details,
            "hint": self.hint,
        }


class DiscoveryError(PFGError):
    """Raised when discovery or configuration fails."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.DISCOVERY,
            kind="DiscoveryError",
            details=details,
            hint=hint,
        )


class MappingError(PFGError):
    """Raised when model mapping or generation cannot be satisfied."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MAPPING,
            kind="MappingError",
            details=details,
            hint=hint,
        )


class EmitError(PFGError):
    """Raised when emitting artifacts fails."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.EMIT,
            kind="EmitError",
            details=details,
            hint=hint,
        )


class UnsafeImportError(PFGError):
    """Raised when the safe importer detects a security violation."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.UNSAFE_IMPORT,
            kind="UnsafeImportViolation",
            details=details,
            hint=hint,
        )


class DiffError(PFGError):
    """Raised when generated artifacts differ from expected output."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.DIFF,
            kind="DiffError",
            details=details,
            hint=hint,
        )


class WatchError(PFGError):
    """Raised when watch mode cannot be started."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.WATCH,
            kind="WatchError",
            details=details,
            hint=hint,
        )


__all__ = [
    "EmitError",
    "DiffError",
    "DiscoveryError",
    "ErrorCode",
    "MappingError",
    "PFGError",
    "WatchError",
    "UnsafeImportError",
]
