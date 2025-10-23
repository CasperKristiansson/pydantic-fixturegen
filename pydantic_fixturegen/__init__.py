"""Top-level package for pydantic-fixturegen."""

from .core.version import get_tool_version

__all__ = ["__version__", "get_tool_version"]

__version__ = get_tool_version()
