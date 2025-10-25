"""Application-level logging helpers with CLI-friendly formatting."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import typer

LOG_LEVEL_ORDER: Final[tuple[str, ...]] = ("error", "warn", "info", "debug", "silent")
LOG_LEVELS: Final[dict[str, int]] = {
    "error": 40,
    "warn": 30,
    "info": 20,
    "debug": 10,
    "silent": 0,
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
        if LOG_LEVELS[level_name] < self.config.level:
            return

        if self.config.json:
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "level": level_name,
                "message": message,
                "details": extras or None,
            }
            sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
            return

        color = {
            "debug": typer.colors.BLUE,
            "info": typer.colors.GREEN,
            "warn": typer.colors.YELLOW,
            "error": typer.colors.RED,
        }[level_name]

        typer.secho(message, fg=color)
        if extras and self.config.level <= LOG_LEVELS["debug"]:
            typer.secho(json.dumps(extras, sort_keys=True, indent=2), fg=typer.colors.BLUE)


_GLOBAL_LOGGER = Logger()


def get_logger() -> Logger:
    return _GLOBAL_LOGGER


__all__ = ["Logger", "LoggerConfig", "LOG_LEVELS", "get_logger"]
