from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic_fixturegen.anonymize import (
    AnonymizeConfig,
    Anonymizer,
    AnonymizeReport,
    build_config_from_rules,
)
from pydantic_fixturegen.logging import Logger, get_logger


def anonymize_payloads(
    records: Iterable[dict[str, Any]],
    *,
    config: AnonymizeConfig,
    logger: Logger | None = None,
) -> tuple[list[dict[str, Any]], AnonymizeReport]:
    """Anonymize ``records`` according to ``config`` and return payload plus report."""

    anonymizer = Anonymizer(config, logger=logger or get_logger())
    record_list = list(records)
    return anonymizer.anonymize_records(record_list)


def anonymize_from_rules(
    records: Iterable[dict[str, Any]],
    *,
    rules_path: Path,
    profile: str | None = None,
    salt: str | None = None,
    entity_field: str | None = None,
    budget_overrides: dict[str, int | None] | None = None,
    logger: Logger | None = None,
) -> tuple[list[dict[str, Any]], AnonymizeReport]:
    """Convenience wrapper that loads ``rules_path`` and executes anonymization."""

    config = build_config_from_rules(
        rules_path=rules_path,
        profile=profile,
        override_salt=salt,
        entity_field=entity_field,
        budget_overrides=budget_overrides,
    )
    return anonymize_payloads(records, config=config, logger=logger)


__all__ = ["anonymize_payloads", "anonymize_from_rules"]
