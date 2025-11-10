"""Shared helpers for silencing noisy third-party warnings."""

from __future__ import annotations

import warnings

WARNING_PATTERNS: tuple[tuple[str, type[Warning]], ...] = (
    (
        r"The `__get_pydantic_core_schema__` method of the `BaseModel` class is deprecated\.",
        Warning,
    ),
    (
        r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
        Warning,
    ),
    (r"ForwardRef\._evaluate is a private API.*", Warning),
    (r"Accessing the 'model_fields' attribute on the instance is deprecated.*", Warning),
)


def apply_warning_filters() -> None:
    for message, category in WARNING_PATTERNS:
        warnings.filterwarnings("ignore", message=message, category=category)


__all__ = ["apply_warning_filters"]
