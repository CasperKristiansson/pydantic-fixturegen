from __future__ import annotations

from typing import ForwardRef

import pytest
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.forward_refs import (
    ForwardRefEntry,
    ForwardReferenceResolutionError,
    configure_forward_refs,
    resolve_forward_ref,
)


class DemoForwardModel:
    pass


def teardown_module() -> None:  # pragma: no cover - reset global registry after tests
    configure_forward_refs(())


def test_resolve_forward_ref_returns_target() -> None:
    configure_forward_refs(
        (
            ForwardRefEntry(
                name="Demo",
                target="tests.core.test_forward_refs:DemoForwardModel",
            ),
        )
    )

    resolved = resolve_forward_ref("Demo")
    assert resolved is not None
    assert resolved.__module__ == "tests.core.test_forward_refs"
    assert resolved.__qualname__ == DemoForwardModel.__qualname__


def test_invalid_forward_ref_target_raises() -> None:
    with pytest.raises(ForwardReferenceResolutionError):
        configure_forward_refs(
            (
                ForwardRefEntry(
                    name="Missing",
                    target="tests.core.test_forward_refs:DoesNotExist",
                ),
            )
        )


def test_schema_module_uses_forward_ref_registry() -> None:
    configure_forward_refs(
        (
            ForwardRefEntry(
                name="Demo",
                target="tests.core.test_forward_refs:DemoForwardModel",
            ),
        )
    )

    annotation = ForwardRef("Demo")
    resolved = schema_module._unwrap_annotation(annotation)
    assert resolved is not None
    assert resolved.__module__ == "tests.core.test_forward_refs"
    assert resolved.__qualname__ == DemoForwardModel.__qualname__
