from __future__ import annotations

import sys
from types import ModuleType

import pytest
from pydantic_fixturegen.core import forward_refs as forward_mod
from pydantic_fixturegen.core.forward_refs import (
    ForwardRefEntry,
    ForwardReferenceConfigurationError,
    ForwardReferenceResolutionError,
    configure_forward_refs,
    resolve_forward_ref,
)


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    configure_forward_refs(())


def _install_module(monkeypatch: pytest.MonkeyPatch, **attrs) -> str:
    module = ModuleType("tests.forward_models")
    for name, value in attrs.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module.__name__


def test_parse_target_requires_module_path() -> None:
    with pytest.raises(ForwardReferenceConfigurationError):
        forward_mod._parse_target("UserModel")  # type: ignore[attr-defined]


def test_configure_forward_refs_rejects_empty_alias() -> None:
    entry = ForwardRefEntry(name=" ", target="pkg:Type")
    with pytest.raises(ForwardReferenceConfigurationError):
        configure_forward_refs([entry])


def test_resolve_forward_ref_returns_cached_type(monkeypatch: pytest.MonkeyPatch) -> None:
    class Demo:
        pass

    module_name = _install_module(monkeypatch, Demo=Demo)
    configure_forward_refs([ForwardRefEntry(name="DemoAlias", target=f"{module_name}:Demo")])

    resolved_first = resolve_forward_ref("DemoAlias")
    resolved_second = resolve_forward_ref("DemoAlias")
    assert resolved_first is Demo
    assert resolved_first is resolved_second


def test_forward_reference_resolution_missing_attr(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = _install_module(monkeypatch)
    entry = ForwardRefEntry(name="Missing", target=f"{module_name}:Nested.Inner")
    with pytest.raises(ForwardReferenceResolutionError):
        configure_forward_refs([entry])

