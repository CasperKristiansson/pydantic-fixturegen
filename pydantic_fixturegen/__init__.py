"""Top-level package for pydantic-fixturegen."""

from __future__ import annotations

from ._warnings import apply_warning_filters
from .core.version import get_tool_version

__all__ = ["__version__", "get_tool_version"]

__version__ = get_tool_version()

apply_warning_filters()
