"""Helpers for managing seed freeze files used for deterministic generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .seed import SeedManager

FREEZE_FILE_BASENAME = ".pfg-seeds.json"
FREEZE_FILE_VERSION = 1


class FreezeStatus(str, Enum):
    """Status classification for freeze entries when resolving seeds."""

    MISSING = "missing"
    STALE = "stale"
    VALID = "valid"


@dataclass(slots=True)
class SeedRecord:
    """Stored seed metadata for a single model."""

    seed: int
    model_digest: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"seed": self.seed}
        if self.model_digest is not None:
            payload["model_digest"] = self.model_digest
        return payload


class SeedFreezeFile:
    """Abstraction over the freeze file storing per-model deterministic seeds."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.exists = False
        self._records: dict[str, SeedRecord] = {}
        self._dirty = False
        self.messages: list[str] = []

    @property
    def records(self) -> dict[str, SeedRecord]:
        return self._records

    @classmethod
    def load(cls, path: Path) -> SeedFreezeFile:
        manager = cls(path)
        if not path.exists():
            return manager

        manager.exists = True
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            manager.messages.append(f"Failed to parse seed freeze file: {exc}")
            return manager

        version = raw.get("version")
        if version != FREEZE_FILE_VERSION:
            manager.messages.append("Seed freeze file version mismatch; ignoring entries")
            return manager

        models = raw.get("models", {})
        if not isinstance(models, dict):
            manager.messages.append("Seed freeze file missing 'models' mapping; ignoring entries")
            return manager

        for identifier, payload in models.items():
            if not isinstance(payload, dict):
                continue
            seed = payload.get("seed")
            if not isinstance(seed, int):
                continue
            record = SeedRecord(
                seed=seed,
                model_digest=payload.get("model_digest"),
            )
            manager._records[identifier] = record
        return manager

    def resolve_seed(
        self, identifier: str, *, model_digest: str | None
    ) -> tuple[int | None, FreezeStatus]:
        record = self._records.get(identifier)
        if record is None:
            return None, FreezeStatus.MISSING

        if model_digest and record.model_digest and record.model_digest != model_digest:
            return record.seed, FreezeStatus.STALE

        if model_digest and record.model_digest is None:
            return record.seed, FreezeStatus.STALE

        return record.seed, FreezeStatus.VALID

    def record_seed(self, identifier: str, seed: int, *, model_digest: str | None) -> None:
        current = self._records.get(identifier)
        new_record = SeedRecord(seed=seed, model_digest=model_digest)
        if (
            current
            and current.seed == new_record.seed
            and current.model_digest == new_record.model_digest
        ):
            return

        self._records[identifier] = new_record
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return

        output = {
            "version": FREEZE_FILE_VERSION,
            "models": {
                identifier: record.to_payload()
                for identifier, record in sorted(self._records.items())
            },
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._dirty = False


def resolve_freeze_path(path_option: Path | None, *, root: Path | None = None) -> Path:
    base = root or Path.cwd()
    if path_option is None:
        return base / FREEZE_FILE_BASENAME

    candidate = Path(path_option)
    if candidate.is_absolute():
        return candidate
    return base / candidate


def canonical_module_name(model: type[BaseModel]) -> str:
    """Return the canonical module name for a dynamically imported model."""

    return getattr(model, "__pfg_canonical_module__", model.__module__)


def model_identifier(model: type[BaseModel]) -> str:
    return f"{canonical_module_name(model)}.{model.__qualname__}"


def compute_model_digest(model: type[BaseModel]) -> str | None:
    try:
        schema = model.model_json_schema()
    except Exception:  # pragma: no cover - defensive
        return None

    serialized = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def derive_default_model_seed(base_seed: int | str | None, identifier: str) -> int:
    manager = SeedManager(seed=base_seed)
    return manager.derive_child_seed(identifier)


__all__ = [
    "FREEZE_FILE_BASENAME",
    "FREEZE_FILE_VERSION",
    "FreezeStatus",
    "canonical_module_name",
    "SeedFreezeFile",
    "compute_model_digest",
    "derive_default_model_seed",
    "model_identifier",
    "resolve_freeze_path",
]
