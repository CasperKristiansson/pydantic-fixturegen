"""Field policy definitions and matching utilities."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


class FieldPolicyConflictError(ValueError):
    """Raised when multiple field policies conflict for the same attribute."""


@dataclass(frozen=True)
class FieldPolicy:
    pattern: str
    options: Mapping[str, Any]
    index: int
    _is_regex: bool = field(init=False, repr=False)
    _regex: re.Pattern[str] | None = field(init=False, repr=False)
    _specificity: tuple[int, int, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        pattern = self.pattern.strip()
        if not pattern:
            raise ValueError("Field policy pattern must be a non-empty string.")

        object.__setattr__(self, "_is_regex", pattern.startswith("re:"))
        if self._is_regex:
            compiled = re.compile(pattern[3:])
            object.__setattr__(self, "_regex", compiled)
            object.__setattr__(self, "_specificity", (1000, -len(pattern), -self.index))
        else:
            wildcard_count = pattern.count("*") + pattern.count("?")
            segments = pattern.count(".") + 1
            specificity = (wildcard_count, -segments, -len(pattern))
            object.__setattr__(self, "_regex", None)
            object.__setattr__(self, "_specificity", specificity)

    @property
    def specificity(self) -> tuple[int, int, int]:
        return self._specificity

    def matches(self, path: str) -> bool:
        if self._is_regex:
            assert self._regex is not None
            return bool(self._regex.fullmatch(path))
        return fnmatch.fnmatchcase(path, self.pattern)


class FieldPolicySet:
    """Collection of field policies with deterministic resolution."""

    def __init__(self, policies: Sequence[FieldPolicy]) -> None:
        self._policies = sorted(policies, key=lambda p: (p.specificity, p.index))

    def resolve(self, path: str, *, aliases: Sequence[str] | None = None) -> Mapping[str, Any]:
        if not self._policies:
            return {}

        applied: dict[str, Any] = {}
        sources: dict[str, str] = {}
        candidates: tuple[str, ...]
        if aliases:
            seen: dict[str, None] = {}
            for candidate in (path, *aliases):
                if candidate and candidate not in seen:
                    seen[candidate] = None
            candidates = tuple(seen.keys())
        else:
            candidates = (path,)

        for policy in self._policies:
            if not any(policy.matches(candidate) for candidate in candidates):
                continue
            for key, value in policy.options.items():
                if value is None:
                    continue
                if key in applied and applied[key] != value:
                    raise FieldPolicyConflictError(
                        f"Conflicting field policies for '{path}' attribute '{key}': "
                        f"{sources[key]!r} vs {policy.pattern!r}"
                    )
                if key not in applied:
                    sources[key] = policy.pattern
                applied[key] = value

        return applied

    def iterable(self) -> Iterable[FieldPolicy]:
        return self._policies


__all__ = [
    "FieldPolicy",
    "FieldPolicyConflictError",
    "FieldPolicySet",
]
