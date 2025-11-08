"""Deterministic anonymization pipeline and helpers."""

from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from faker import Faker

from pydantic_fixturegen.core.config import tomllib as config_tomllib
from pydantic_fixturegen.core.errors import EmitError
from pydantic_fixturegen.core.privacy_profiles import normalize_privacy_profile_name
from pydantic_fixturegen.logging import Logger, get_logger

DEFAULT_SALT = "pfg-anonymize"


@dataclass(slots=True)
class AnonymizeBudget:
    """Privacy budget thresholds enforced after each run."""

    max_required_rule_misses: int | None = 0
    max_rule_failures: int | None = 0


@dataclass(slots=True)
class AnonymizeRule:
    """Rule mapping dotted paths to anonymization strategies."""

    pattern: str
    strategy: str
    provider: str | None = None
    hash_algorithm: str = "sha256"
    mask_value: str | None = None
    mask_char: str = "*"
    required: bool = False

    def matches(self, path: str) -> bool:
        if fnmatch.fnmatchcase(path, self.pattern):
            return True
        if path.startswith("$."):
            trimmed = path[2:]
        elif path.startswith("$"):
            trimmed = path[1:]
        else:
            trimmed = path
        return fnmatch.fnmatchcase(trimmed, self.pattern)


@dataclass(slots=True)
class AnonymizeConfig:
    """Resolved config feeding the anonymizer."""

    rules: list[AnonymizeRule]
    salt: str = DEFAULT_SALT
    entity_field: str | None = None
    budget: AnonymizeBudget = field(default_factory=AnonymizeBudget)
    profile: str | None = None


@dataclass(slots=True)
class DiffEntry:
    path: str
    before: Any
    after: Any
    strategy: str
    record_index: int


@dataclass(slots=True)
class AnonymizeReport:
    records_processed: int
    fields_anonymized: int
    strategy_counts: dict[str, int]
    rule_matches: dict[str, int]
    rule_failures: dict[str, int]
    required_rule_misses: int
    diffs: list[DiffEntry]
    doctor_summary: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "records_processed": self.records_processed,
            "fields_anonymized": self.fields_anonymized,
            "strategies": self.strategy_counts,
            "rules": self.rule_matches,
            "rule_failures": self.rule_failures,
            "required_rule_misses": self.required_rule_misses,
            "diffs": [
                {
                    "path": diff.path,
                    "before": diff.before,
                    "after": diff.after,
                    "strategy": diff.strategy,
                    "record_index": diff.record_index,
                }
                for diff in self.diffs
            ],
            "doctor_summary": self.doctor_summary,
        }


PROFILE_RULESETS: dict[str, dict[str, Any]] = {
    "pii-safe": {
        "rules": [
            {"pattern": "*.email", "strategy": "faker", "provider": "email", "required": True},
            {"pattern": "*.Email", "strategy": "faker", "provider": "email", "required": True},
            {
                "pattern": "*.phone*",
                "strategy": "faker",
                "provider": "phone_number",
                "required": True,
            },
            {
                "pattern": "*.Phone*",
                "strategy": "faker",
                "provider": "phone_number",
                "required": True,
            },
            {"pattern": "*.ssn", "strategy": "hash", "hash_algorithm": "sha256", "required": True},
            {
                "pattern": "*.tax_id",
                "strategy": "hash",
                "hash_algorithm": "sha256",
                "required": True,
            },
        ],
        "budget": {"max_required_rule_misses": 0, "max_rule_failures": 0},
    },
    "realistic": {
        "rules": [
            {"pattern": "*.email", "strategy": "faker", "provider": "email", "required": False},
            {
                "pattern": "*.phone*",
                "strategy": "faker",
                "provider": "phone_number",
                "required": False,
            },
            {"pattern": "*.name", "strategy": "faker", "provider": "name", "required": False},
        ],
        "budget": {"max_required_rule_misses": 5, "max_rule_failures": 0},
    },
    "edge": {
        "rules": [
            {"pattern": "*.limit", "strategy": "hash", "hash_algorithm": "sha1", "required": False},
            {"pattern": "*.count", "strategy": "hash", "hash_algorithm": "sha1", "required": False},
        ],
        "budget": {"max_required_rule_misses": 10, "max_rule_failures": 2},
    },
    "adversarial": {
        "rules": [
            {"pattern": "*.id", "strategy": "hash", "hash_algorithm": "sha1", "required": True},
            {"pattern": "*.token", "strategy": "mask", "mask_char": "#", "required": True},
        ],
        "budget": {"max_required_rule_misses": 1, "max_rule_failures": 0},
    },
}


class Anonymizer:
    """Apply anonymization rules with deterministic pseudonyms."""

    def __init__(
        self,
        config: AnonymizeConfig,
        *,
        logger: Logger | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or get_logger()
        self._faker_factory: Callable[[int], Faker] = lambda seed: _seeded_faker(seed)
        self._rule_stats: dict[str, int] = {rule.pattern: 0 for rule in config.rules}
        self._rule_failures: dict[str, int] = {}
        self._diff_entries: list[DiffEntry] = []
        self._strategy_counts: dict[str, int] = {}

    def anonymize_records(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], AnonymizeReport]:
        anonymized: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            entity_id = self._resolve_entity(record, index)
            clone = copy.deepcopy(record)
            updated = self._process_node(clone, path="$", entity_id=entity_id, record_index=index)
            anonymized.append(updated)

        required_rule_misses = sum(
            1
            for rule in self.config.rules
            if rule.required and self._rule_stats.get(rule.pattern, 0) == 0
        )
        self._enforce_budgets(required_rule_misses)

        report = AnonymizeReport(
            records_processed=len(records),
            fields_anonymized=sum(self._strategy_counts.values()),
            strategy_counts=dict(self._strategy_counts),
            rule_matches=dict(self._rule_stats),
            rule_failures=dict(self._rule_failures),
            required_rule_misses=required_rule_misses,
            diffs=list(self._diff_entries),
        )
        return anonymized, report

    # --------------------------------------------------------------------- internals
    def _resolve_entity(self, record: dict[str, Any], fallback: int) -> str:
        if not self.config.entity_field:
            return f"record-{fallback}"
        parts = self.config.entity_field.split(".")
        current: Any = record
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return f"record-{fallback}"
        return str(current)

    def _process_node(
        self,
        value: Any,
        *,
        path: str,
        entity_id: str,
        record_index: int,
    ) -> Any:
        if isinstance(value, dict):
            for key, child in value.items():
                sub_path = f"{path}.{key}" if path else key
                value[key] = self._process_node(
                    child,
                    path=sub_path,
                    entity_id=entity_id,
                    record_index=record_index,
                )
            return value
        if isinstance(value, list):
            for idx, child in enumerate(value):
                token = f"{path}[{idx}]" if path else f"[{idx}]"
                value[idx] = self._process_node(
                    child,
                    path=token,
                    entity_id=entity_id,
                    record_index=record_index,
                )
            return value
        return self._apply_strategies(
            value=value,
            path=path,
            entity_id=entity_id,
            record_index=record_index,
        )

    def _apply_strategies(
        self,
        *,
        value: Any,
        path: str,
        entity_id: str,
        record_index: int,
    ) -> Any:
        for rule in self.config.rules:
            if not rule.matches(path):
                continue
            try:
                new_value = self._execute_strategy(rule, value, path, entity_id)
            except Exception as exc:  # pragma: no cover - defensive fallback
                self.logger.error(
                    "Rule execution failed",
                    event="anonymize_rule_failure",
                    pattern=rule.pattern,
                    path=path,
                    error=str(exc),
                )
                self._rule_failures[rule.pattern] = self._rule_failures.get(rule.pattern, 0) + 1
                continue
            self._rule_stats[rule.pattern] = self._rule_stats.get(rule.pattern, 0) + 1
            if new_value != value:
                if len(self._diff_entries) < 50:
                    self._diff_entries.append(
                        DiffEntry(
                            path=path,
                            before=value,
                            after=new_value,
                            strategy=rule.strategy,
                            record_index=record_index,
                        )
                    )
                self._strategy_counts[rule.strategy] = (
                    self._strategy_counts.get(rule.strategy, 0) + 1
                )
            return new_value
        return value

    def _execute_strategy(
        self,
        rule: AnonymizeRule,
        value: Any,
        path: str,
        entity_id: str,
    ) -> Any:
        seed = self._derive_seed(entity_id, path, value)
        if rule.strategy == "faker":
            if not rule.provider:
                raise EmitError(
                    f"Rule '{rule.pattern}' uses 'faker' strategy but no provider was supplied.",
                )
            faker = self._faker_factory(seed)
            provider = getattr(faker, rule.provider, None)
            if provider is None or not callable(provider):
                raise EmitError(
                    f"Unknown Faker provider '{rule.provider}' for rule '{rule.pattern}'.",
                )
            return provider()
        if rule.strategy == "hash":
            algorithm = rule.hash_algorithm or "sha256"
            try:
                hasher = hashlib.new(algorithm)
            except ValueError as exc:  # pragma: no cover - depends on hashlib build
                raise EmitError(
                    f"Unknown hash algorithm '{algorithm}' for rule '{rule.pattern}'."
                ) from exc
            hasher.update(self.config.salt.encode("utf-8"))
            hasher.update(str(value).encode("utf-8"))
            return hasher.hexdigest()
        if rule.strategy == "mask":
            if rule.mask_value is not None:
                return rule.mask_value
            base = str(value)
            mask_char = rule.mask_char or "*"
            if not base:
                return mask_char
            return mask_char * len(base)
        raise EmitError(
            f"Unsupported anonymization strategy '{rule.strategy}' in rule '{rule.pattern}'.",
        )

    def _derive_seed(self, entity_id: str, path: str, value: Any) -> int:
        digest = hashlib.blake2b(digest_size=16)
        digest.update(self.config.salt.encode("utf-8"))
        digest.update(entity_id.encode("utf-8"))
        digest.update(path.encode("utf-8"))
        digest.update(str(value).encode("utf-8"))
        return int.from_bytes(digest.digest(), "big")

    def _enforce_budgets(self, required_rule_misses: int) -> None:
        budget = self.config.budget
        if (
            budget.max_required_rule_misses is not None
            and required_rule_misses > budget.max_required_rule_misses
        ):
            raise EmitError(
                "Required anonymization rules were not applied "
                f"({required_rule_misses} > {budget.max_required_rule_misses})."
            )
        total_failures = sum(self._rule_failures.values())
        if (
            budget.max_rule_failures is not None
            and total_failures > budget.max_rule_failures
        ):
            raise EmitError(
                f"Rule execution failures exceeded budget "
                f"({total_failures} > {budget.max_rule_failures})."
            )


def _seeded_faker(seed: int) -> Faker:
    faker = Faker()
    faker.seed_instance(seed % (2**31))
    return faker


def load_rules_document(path: Path) -> dict[str, Any]:
    raw: dict[str, Any]
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except Exception as exc:  # pragma: no cover - import guard
            raise EmitError(
                "PyYAML is required to load anonymizer rules from YAML files.",
                details={"path": str(path)},
            ) from exc
        raw = yaml.safe_load(text) or {}
    elif suffix == ".json":
        raw = json.loads(text)
    else:
        with path.open("rb") as fh:
            raw = config_tomllib.load(fh)
    if not isinstance(raw, dict):
        raise EmitError(
            "Anonymization rule files must contain a mapping at the top level.",
            details={"path": str(path)},
        )
    return raw


def build_config_from_rules(
    *,
    rules_path: Path,
    profile: str | None = None,
    override_salt: str | None = None,
    entity_field: str | None = None,
    budget_overrides: dict[str, int | None] | None = None,
) -> AnonymizeConfig:
    document = load_rules_document(rules_path)
    section = document.get("anonymize", document)
    normalized_profile: str | None = None
    resolved_rules: list[AnonymizeRule] = []
    resolved_budget = AnonymizeBudget()

    if profile:
        normalized_profile = normalize_privacy_profile_name(profile)
        preset = PROFILE_RULESETS.get(normalized_profile)
        if preset:
            resolved_rules.extend(_build_rules_from_dicts(preset.get("rules", [])))
            preset_budget = preset.get("budget", {})
            resolved_budget = _budget_from_dict(preset_budget)

    file_rules = section.get("rules", [])
    resolved_rules.extend(_build_rules_from_dicts(file_rules))

    config_salt = (
        override_salt
        or section.get("salt")
        or (document.get("anonymize", {}).get("salt") if "anonymize" in document else None)
        or DEFAULT_SALT
    )

    derived_entity = entity_field or section.get("entity_field")
    if not resolved_rules:
        raise EmitError(
            "No anonymization rules were defined. Provide at least one rule.",
            details={"path": str(rules_path)},
        )

    file_budget = section.get("budget")
    if file_budget:
        budget = _budget_from_dict(file_budget)
        resolved_budget = _merge_budgets(resolved_budget, budget)
    if budget_overrides:
        override_budget = _budget_from_dict(budget_overrides)
        resolved_budget = _merge_budgets(resolved_budget, override_budget)

    return AnonymizeConfig(
        rules=resolved_rules,
        salt=config_salt,
        entity_field=derived_entity,
        budget=resolved_budget,
        profile=normalized_profile,
    )


def _build_rules_from_dicts(entries: list[dict[str, Any]]) -> list[AnonymizeRule]:
    rules: list[AnonymizeRule] = []
    for entry in entries:
        pattern = entry.get("pattern")
        strategy = entry.get("strategy")
        if not pattern or not strategy:
            raise EmitError("Each anonymization rule must define 'pattern' and 'strategy'.")
        rules.append(
            AnonymizeRule(
                pattern=pattern,
                strategy=strategy,
                provider=entry.get("provider"),
                hash_algorithm=entry.get("hash_algorithm", "sha256"),
                mask_value=entry.get("mask_value"),
                mask_char=entry.get("mask_char", "*"),
                required=bool(entry.get("required", False)),
            )
        )
    return rules


def _budget_from_dict(raw: dict[str, Any]) -> AnonymizeBudget:
    budget = AnonymizeBudget()
    if "max_required_rule_misses" in raw:
        budget.max_required_rule_misses = _coerce_budget_value(raw["max_required_rule_misses"])
    if "max_rule_failures" in raw:
        budget.max_rule_failures = _coerce_budget_value(raw["max_rule_failures"])
    return budget


def _merge_budgets(base: AnonymizeBudget, overrides: AnonymizeBudget) -> AnonymizeBudget:
    return AnonymizeBudget(
        max_required_rule_misses=(
            overrides.max_required_rule_misses
            if overrides.max_required_rule_misses is not None
            else base.max_required_rule_misses
        ),
        max_rule_failures=(
            overrides.max_rule_failures
            if overrides.max_rule_failures is not None
            else base.max_rule_failures
        ),
    )


def _coerce_budget_value(value: Any) -> int | None:
    if value is None:
        return None
    coerced = int(value)
    if coerced < 0:
        raise EmitError("Budget thresholds must be >= 0.")
    return coerced


__all__ = [
    "AnonymizeBudget",
    "AnonymizeConfig",
    "AnonymizeReport",
    "AnonymizeRule",
    "Anonymizer",
    "build_config_from_rules",
    "load_rules_document",
    "PROFILE_RULESETS",
]
