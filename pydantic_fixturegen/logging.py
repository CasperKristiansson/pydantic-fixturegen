"""Application-level logging helpers with CLI-friendly formatting."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import typer

LOG_LEVEL_ORDER: Final[tuple[str, ...]] = ("silent", "error", "warn", "info", "debug")
LOG_LEVELS: Final[dict[str, int]] = {
    "silent": 100,
    "error": 40,
    "warn": 30,
    "info": 20,
    "debug": 10,
}


# Index in LOG_LEVEL_ORDER representing the default "info" verbosity tier
DEFAULT_VERBOSITY_INDEX: Final[int] = LOG_LEVEL_ORDER.index("info")


_COLOR_BY_LEVEL: Final[dict[str, str]] = {
    "debug": typer.colors.BLUE,
    "info": typer.colors.GREEN,
    "warn": typer.colors.YELLOW,
    "error": typer.colors.RED,
}


@dataclass(slots=True)
class LoggerConfig:
    level: int = LOG_LEVELS["info"]
    json: bool = False


class Logger:
    def __init__(self, config: LoggerConfig | None = None) -> None:
        self.config = config or LoggerConfig()

    def configure(self, *, level: str | None = None, json_mode: bool | None = None) -> None:
        if level is not None:
            canonical = level.lower()
            if canonical not in LOG_LEVELS:
                raise ValueError(f"Unknown log level: {level}")
            self.config.level = LOG_LEVELS[canonical]
        if json_mode is not None:
            self.config.json = json_mode

    def debug(self, message: str, **extras: Any) -> None:
        self._emit("debug", message, **extras)

    def info(self, message: str, **extras: Any) -> None:
        self._emit("info", message, **extras)

    def warn(self, message: str, **extras: Any) -> None:
        self._emit("warn", message, **extras)

    def error(self, message: str, **extras: Any) -> None:
        self._emit("error", message, **extras)

    def _emit(self, level_name: str, message: str, **extras: Any) -> None:
        level_value = LOG_LEVELS.get(level_name)
        if level_value is None:
            raise ValueError(f"Unknown log level: {level_name}")

        if level_value < self.config.level:
            return

        payload_context = dict(extras)
        event_name = payload_context.pop("event", message)

        if self.config.json:
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "level": level_name,
                "event": event_name,
                "message": message,
                "context": payload_context or None,
            }
            sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
            return

        stream_to_err = level_name in {"warn", "error"}
        color = _COLOR_BY_LEVEL.get(level_name, typer.colors.WHITE)

        typer.secho(message, fg=color, err=stream_to_err)
        if payload_context and self.config.level <= LOG_LEVELS["debug"]:
            typer.secho(
                json.dumps(payload_context, sort_keys=True, indent=2),
                fg=_COLOR_BY_LEVEL["debug"],
                err=stream_to_err,
            )


_GLOBAL_LOGGER = Logger()


def get_logger() -> Logger:
    return _GLOBAL_LOGGER


__all__ = [
    "Logger",
    "LoggerConfig",
    "LOG_LEVELS",
    "LOG_LEVEL_ORDER",
    "DEFAULT_VERBOSITY_INDEX",
    "get_logger",
]
