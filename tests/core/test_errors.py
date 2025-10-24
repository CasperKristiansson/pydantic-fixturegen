from __future__ import annotations

import json

import pytest
from pydantic_fixturegen.core.errors import (
    DiscoveryError,
    EmitError,
    ErrorCode,
    MappingError,
    PFGError,
    UnsafeImportError,
)


def test_error_payload_contents() -> None:
    error = DiscoveryError("Missing module", details={"path": "foo.py"}, hint="Check the path.")
    payload = error.to_payload()

    assert payload["code"] == int(ErrorCode.DISCOVERY)
    assert payload["kind"] == "DiscoveryError"
    assert payload["message"] == "Missing module"
    assert payload["details"] == {"path": "foo.py"}
    assert payload["hint"] == "Check the path."


def test_emit_error_serialisation_roundtrip() -> None:
    error = EmitError("Emitter failed", details={"out": "fixtures.py"})
    payload = error.to_payload()

    encoded = json.dumps({"error": payload})
    decoded = json.loads(encoded)
    assert decoded["error"]["code"] == 30
    assert decoded["error"]["details"]["out"] == "fixtures.py"


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (MappingError("cannot map"), ErrorCode.MAPPING),
        (UnsafeImportError("network access disabled"), ErrorCode.UNSAFE_IMPORT),
    ],
)
def test_error_code_mapping(exc: PFGError, expected_code: ErrorCode) -> None:
    assert exc.code == expected_code
