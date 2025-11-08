"""Constraint enforcement reporting utilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .schema import FieldSummary
from .seed_freeze import canonical_module_name


@dataclass(slots=True)
class FieldFailure:
    location: tuple[str, ...]
    message: str
    error_type: str | None
    value: Any
    hint: str


@dataclass(slots=True)
class FieldStats:
    constraints: dict[str, Any] | None
    attempts: int = 0
    successes: int = 0
    failures: list[FieldFailure] = field(default_factory=list)


@dataclass(slots=True)
class ModelStats:
    attempts: int = 0
    successes: int = 0
    fields: dict[str, FieldStats] = field(default_factory=dict)


@dataclass(slots=True)
class _AttemptContext:
    model_key: str
    field_summaries: dict[str, FieldSummary] = field(default_factory=dict)
    field_values: dict[str, Any] = field(default_factory=dict)


class ConstraintReporter:
    """Collect constraint enforcement metrics during generation."""

    def __init__(self) -> None:
        self._models: dict[str, ModelStats] = {}
        self._stack: list[_AttemptContext] = []

    @staticmethod
    def _model_key(model: type[BaseModel]) -> str:
        return f"{canonical_module_name(model)}.{model.__qualname__}"

    def begin_model(self, model: type[BaseModel]) -> None:
        key = self._model_key(model)
        stats = self._models.setdefault(key, ModelStats())
        stats.attempts += 1
        self._stack.append(_AttemptContext(model_key=key))

    def record_field_attempt(
        self,
        model: type[BaseModel],
        field_name: str,
        summary: FieldSummary,
    ) -> None:
        if not self._stack:
            return
        ctx = self._stack[-1]
        ctx.field_summaries[field_name] = summary
        stats = self._models.setdefault(ctx.model_key, ModelStats())
        constraints_snapshot = _constraints_snapshot(summary)
        field_stats = stats.fields.setdefault(
            field_name,
            FieldStats(constraints=constraints_snapshot),
        )
        if summary.constraints.has_constraints():
            field_stats.attempts += 1

    def record_field_value(self, field_name: str, value: Any) -> None:
        if not self._stack:
            return
        ctx = self._stack[-1]
        ctx.field_values[field_name] = value

    def finish_model(
        self,
        model: type[BaseModel],
        *,
        success: bool,
        errors: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        if not self._stack:
            return
        ctx = self._stack.pop()
        stats = self._models.setdefault(ctx.model_key, ModelStats())
        if success:
            stats.successes += 1
            for field_name, summary in ctx.field_summaries.items():
                if summary.constraints.has_constraints():
                    field_stats = stats.fields.setdefault(
                        field_name,
                        FieldStats(constraints=_constraints_snapshot(summary)),
                    )
                    field_stats.successes += 1
            return

        if errors:
            self._record_failures(stats, ctx, errors)

    def summary(self) -> dict[str, Any]:
        models_summary: list[dict[str, Any]] = []
        total_failures = 0
        for model_key, stats in self._models.items():
            field_entries: list[dict[str, Any]] = []
            for field_name, field_stats in stats.fields.items():
                if not field_stats.constraints and not field_stats.failures:
                    continue
                failures = [
                    {
                        "location": list(failure.location),
                        "message": failure.message,
                        "error_type": failure.error_type,
                        "value": failure.value,
                        "hint": failure.hint,
                    }
                    for failure in field_stats.failures
                ]
                total_failures += len(failures)
                field_entries.append(
                    {
                        "name": field_name,
                        "constraints": field_stats.constraints,
                        "attempts": field_stats.attempts,
                        "successes": field_stats.successes,
                        "failures": failures,
                    }
                )
            if not field_entries:
                continue
            models_summary.append(
                {
                    "model": model_key,
                    "attempts": stats.attempts,
                    "successes": stats.successes,
                    "fields": field_entries,
                }
            )

        total_models = sum(stats.attempts for stats in self._models.values())
        models_with_failures = sum(
            1 for entry in models_summary if any(field["failures"] for field in entry["fields"])
        )

        return {
            "models": models_summary,
            "total_models": total_models,
            "models_with_failures": models_with_failures,
            "total_failures": total_failures,
        }

    def has_failures(self) -> bool:
        return any(
            field.failures for stats in self._models.values() for field in stats.fields.values()
        )

    def merge_from(self, other: ConstraintReporter) -> None:
        for model_key, other_stats in other._models.items():
            stats = self._models.setdefault(model_key, ModelStats())
            stats.attempts += other_stats.attempts
            stats.successes += other_stats.successes
            for field_name, other_field in other_stats.fields.items():
                field_stats = stats.fields.setdefault(
                    field_name,
                    FieldStats(constraints=other_field.constraints),
                )
                if field_stats.constraints is None and other_field.constraints is not None:
                    field_stats.constraints = other_field.constraints
                field_stats.attempts += other_field.attempts
                field_stats.successes += other_field.successes
                field_stats.failures.extend(other_field.failures)

    def _record_failures(
        self,
        stats: ModelStats,
        ctx: _AttemptContext,
        errors: Iterable[Mapping[str, Any]],
    ) -> None:
        for error in errors:
            loc_raw = tuple(error.get("loc", ()))
            if not loc_raw:
                continue
            top_field = str(loc_raw[0])
            summary = ctx.field_summaries.get(top_field)
            field_stats = stats.fields.setdefault(
                top_field,
                FieldStats(constraints=_constraints_snapshot(summary)),
            )
            value = _extract_value(ctx.field_values.get(top_field), loc_raw[1:])
            error_type = error.get("type")
            message = error.get("msg", "")
            failure = FieldFailure(
                location=tuple(str(part) for part in loc_raw),
                message=message,
                error_type=error_type,
                value=value,
                hint=_hint_for_error(error_type, top_field, summary, message),
            )
            field_stats.failures.append(failure)


def _constraints_snapshot(summary: FieldSummary | None) -> dict[str, Any] | None:
    if summary is None or not summary.constraints.has_constraints():
        return None
    constraints = summary.constraints
    data: dict[str, Any] = {}
    if constraints.ge is not None:
        data["ge"] = constraints.ge
    if constraints.gt is not None:
        data["gt"] = constraints.gt
    if constraints.le is not None:
        data["le"] = constraints.le
    if constraints.lt is not None:
        data["lt"] = constraints.lt
    if constraints.multiple_of is not None:
        data["multiple_of"] = constraints.multiple_of
    if constraints.min_length is not None:
        data["min_length"] = constraints.min_length
    if constraints.max_length is not None:
        data["max_length"] = constraints.max_length
    if constraints.pattern is not None:
        data["pattern"] = constraints.pattern
    if constraints.max_digits is not None:
        data["max_digits"] = constraints.max_digits
    if constraints.decimal_places is not None:
        data["decimal_places"] = constraints.decimal_places
    return data


def _extract_value(base: Any, path: tuple[Any, ...]) -> Any:
    current = base
    for part in path:
        if current is None:
            return None
        if isinstance(current, BaseModel):
            current = getattr(current, str(part), None)
            continue
        if isinstance(current, dict):
            current = current.get(part) if part in current else current.get(str(part))
            continue
        if isinstance(current, list | tuple) and isinstance(part, int):
            if 0 <= part < len(current):
                current = current[part]
            else:
                return None
            continue
        try:
            current = getattr(current, str(part))
        except AttributeError:
            return None
    return current


def _hint_for_error(
    error_type: str | None,
    field_name: str,
    summary: FieldSummary | None,
    message: str,
) -> str:
    base_hint = (
        "Configure an override for '" + field_name + "' via `[tool.pydantic_fixturegen.overrides]` "
        "or adjust the model constraints."
    )
    if not error_type:
        return base_hint
    if error_type.startswith("value_error.number"):
        return "Adjust numeric bounds or override the provider for '" + field_name + "'."
    if error_type.startswith("value_error.any_str"):
        return (
            "Adjust string length/pattern constraints or override the provider for '"
            + field_name
            + "'."
        )
    if error_type.startswith("value_error.list") or error_type.startswith("value_error.collection"):
        return (
            "Adjust collection size constraints or provide a custom generator for '"
            + field_name
            + "'."
        )
    if error_type.startswith("type_error"):
        return (
            "Ensure the generated value for '"
            + field_name
            + "' matches the expected type or supply an override."
        )
    return base_hint


__all__ = [
    "ConstraintReporter",
    "FieldFailure",
    "FieldStats",
    "ModelStats",
]
