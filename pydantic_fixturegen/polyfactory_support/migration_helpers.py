"""Helper callables used by Polyfactory migration overrides."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Any, cast


def _resolve_callable(path: str) -> Callable[..., Any]:
    if not path:
        raise ValueError("callable path must be a non-empty string")
    module_name: str
    attr_path: str
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)
    module = import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise AttributeError(f"Callable '{path}' could not be resolved.")
        target = getattr(target, part)
    if not callable(target):
        raise TypeError(f"Target '{path}' is not callable.")
    return cast(Callable[..., Any], target)


def invoke_use(
    _context: Any,
    target_path: str,
    call_args: Sequence[Any] | None = None,
    call_kwargs: Mapping[str, Any] | None = None,
) -> Any:
    """Adapter used by fixturegen overrides to mirror `Use` semantics."""

    func = _resolve_callable(target_path)
    args = tuple(call_args or ())
    kwargs = dict(call_kwargs or {})
    return func(*args, **kwargs)


def invoke_post_generate(
    value: Any,
    context: Any,
    target_path: str,
    call_args: Sequence[Any] | None = None,
    call_kwargs: Mapping[str, Any] | None = None,
) -> Any:
    """Adapter that mimics Polyfactory `PostGenerated` callbacks."""

    func = _resolve_callable(target_path)
    args = tuple(call_args or ())
    kwargs = dict(call_kwargs or {})
    values = dict(getattr(context, "values", {}))
    values.setdefault(context.field_name, value)
    return func(context.field_name, values, *args, **kwargs)


__all__ = ["invoke_use", "invoke_post_generate"]
