"""Top-level package for pydantic-fixturegen."""

from __future__ import annotations

import warnings

from .core.version import get_tool_version

__all__ = ["__version__", "get_tool_version"]

__version__ = get_tool_version()

warnings.filterwarnings(
    "ignore",
    message=(r"The `__get_pydantic_core_schema__` method of the `BaseModel` class is deprecated\."),
    category=DeprecationWarning,
)
