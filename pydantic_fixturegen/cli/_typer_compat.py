"""Compatibility helpers for Typer + Click interactions."""

from __future__ import annotations

from typing import Any, cast

from typer import core


def _call_type_metavar(param: Any, ctx: Any) -> str | None:
    getter = getattr(param.type, "get_metavar", None)
    if getter is None:
        return None
    try:
        return cast(str | None, getter(param, ctx))
    except TypeError:
        return cast(str | None, getter(param))


def _patched_argument_make_metavar(self: Any, ctx: Any | None = None) -> str:
    if self.metavar is not None:
        return cast(str, self.metavar)

    var: str = (self.name or "").upper()
    if not getattr(self, "required", False):
        var = f"[{var}]"

    type_var = _call_type_metavar(self, ctx)
    if type_var:
        var += f":{type_var}"

    if getattr(self, "nargs", 1) != 1:
        var += "..."
    return var


def _patched_option_make_metavar(self: Any, ctx: Any | None = None) -> str:
    if self.metavar is not None:
        return cast(str, self.metavar)

    metavar: str | None = _call_type_metavar(self, ctx)
    if metavar is None:
        metavar = getattr(self.type, "name", "").upper()

    if getattr(self, "nargs", 1) != 1:
        metavar += "..."
    return metavar


def ensure_typer_compat() -> None:
    core.TyperArgument.make_metavar = _patched_argument_make_metavar  # type: ignore[method-assign]
    core.TyperOption.make_metavar = _patched_option_make_metavar  # type: ignore[method-assign]


ensure_typer_compat()


__all__ = ["ensure_typer_compat"]
