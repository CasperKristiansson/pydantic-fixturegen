from __future__ import annotations

from types import SimpleNamespace

from pydantic_fixturegen.cli import _typer_compat as compat


class _CtxAwareType:
    def __init__(self, label: str) -> None:
        self.label = label

    def get_metavar(self, param: SimpleNamespace, ctx: str) -> str:
        return f"{param.name}:{ctx}:{self.label}"


class _LegacyType:
    def __init__(self, label: str) -> None:
        self.label = label

    def get_metavar(self, param: SimpleNamespace) -> str:
        return f"{param.name}-{self.label}"


def test_call_type_metavar_prefers_context_aware_getter() -> None:
    param = SimpleNamespace(type=_CtxAwareType("X"), name="value")

    result = compat._call_type_metavar(param, ctx="CTX")  # type: ignore[arg-type]

    assert result == "value:CTX:X"


def test_call_type_metavar_handles_legacy_signature() -> None:
    param = SimpleNamespace(type=_LegacyType("legacy"), name="value")

    result = compat._call_type_metavar(param, ctx="ignored")  # type: ignore[arg-type]

    assert result == "value-legacy"


def test_argument_make_metavar_builds_composite_label() -> None:
    param = SimpleNamespace(
        metavar=None,
        name="sample",
        required=False,
        type=_CtxAwareType("A"),
        nargs=2,
    )

    result = compat._patched_argument_make_metavar(param, ctx="CTX")  # type: ignore[arg-type]

    assert result == "[SAMPLE]:sample:CTX:A..."


def test_option_make_metavar_uses_existing_and_type_name() -> None:
    fixed = SimpleNamespace(metavar="CUSTOM", type=_CtxAwareType("B"), nargs=1)
    assert compat._patched_option_make_metavar(fixed) == "CUSTOM"

    auto = SimpleNamespace(metavar=None, type=SimpleNamespace(name="path"), nargs=3)
    assert compat._patched_option_make_metavar(auto) == "PATH..."


def test_argument_make_metavar_uses_explicit_value() -> None:
    param = SimpleNamespace(metavar="VALUE", name="ignored")

    assert compat._patched_argument_make_metavar(param) == "VALUE"


def test_option_make_metavar_uses_callable_type_value() -> None:
    class CustomType:
        def get_metavar(self, param: SimpleNamespace, ctx: object) -> str:
            return "custom"

    param = SimpleNamespace(metavar=None, type=CustomType(), nargs=1)

    assert compat._patched_option_make_metavar(param) == "custom"
