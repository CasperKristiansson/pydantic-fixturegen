from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_fixturegen.anonymize.pipeline import (
    AnonymizeBudget,
    AnonymizeConfig,
    Anonymizer,
    AnonymizeRule,
    build_config_from_rules,
    load_rules_document,
)
from pydantic_fixturegen.core.errors import EmitError


def test_faker_strategy_deterministic() -> None:
    config = AnonymizeConfig(
        rules=[AnonymizeRule(pattern="email", strategy="faker", provider="email", required=True)],
        salt="demo",
    )
    anonymizer = Anonymizer(config)
    records = [{"email": "user@example.com"}]
    anonymized, report = anonymizer.anonymize_records(records)
    first = anonymized[0]["email"]
    assert first != "user@example.com"
    assert report.fields_anonymized == 1

    anonymizer_two = Anonymizer(config)
    anonymized_second, _ = anonymizer_two.anonymize_records(records)
    assert anonymized_second[0]["email"] == first


def test_hash_and_mask_strategies() -> None:
    config = AnonymizeConfig(
        rules=[
            AnonymizeRule(pattern="record.ssn", strategy="hash", hash_algorithm="sha256"),
            AnonymizeRule(pattern="record.token", strategy="mask", mask_char="#"),
        ],
        salt="static",
    )
    anonymizer = Anonymizer(config)
    anonymized, _ = anonymizer.anonymize_records([{"record": {"ssn": "1234", "token": "abcdef"}}])
    payload = anonymized[0]["record"]
    assert payload["ssn"] != "1234"
    assert len(payload["ssn"]) == 64
    assert payload["token"] == "######"


def test_rule_match_trims_root_prefix() -> None:
    rule = AnonymizeRule(pattern="email", strategy="mask")
    assert rule.matches("$.email")


def test_required_rule_budget_enforced() -> None:
    config = AnonymizeConfig(
        rules=[AnonymizeRule(pattern="secret.value", strategy="mask", required=True)],
        budget=AnonymizeBudget(max_required_rule_misses=0),
    )
    anonymizer = Anonymizer(config)
    with pytest.raises(EmitError, match="Required anonymization rules were not applied"):
        anonymizer.anonymize_records([{"other": "data"}])


def test_build_config_from_rules_merges_profile(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.toml"
    rules_file.write_text(
        """
[anonymize]
salt = "demo"

  [[anonymize.rules]]
  pattern = "*.name"
  strategy = "faker"
  provider = "name"
""",
        encoding="utf-8",
    )
    config = build_config_from_rules(rules_path=rules_file, profile="pii-safe")
    patterns = [rule.pattern for rule in config.rules]
    assert "*.name" in patterns
    assert "*.email" in patterns  # from profile preset
    assert config.salt == "demo"


def test_build_config_with_budget_override(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        json.dumps(
            {
                "anonymize": {
                    "salt": "external",
                    "rules": [
                        {
                            "pattern": "*.token",
                            "strategy": "mask",
                            "mask_value": "X",
                            "required": True,
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    config = build_config_from_rules(
        rules_path=rules_file,
        budget_overrides={"max_required_rule_misses": 2},
        entity_field="user.id",
    )
    assert config.budget.max_required_rule_misses == 2
    assert config.entity_field == "user.id"


def test_load_rules_document_json(tmp_path: Path) -> None:
    rules_file = tmp_path / "ruleset.json"
    payload = {"anonymize": {"rules": [{"pattern": "*.id", "strategy": "hash"}]}}
    rules_file.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_rules_document(rules_file)
    assert loaded["anonymize"]["rules"][0]["strategy"] == "hash"


def test_anonymizer_entity_resolution_and_lists() -> None:
    config = AnonymizeConfig(
        rules=[
            AnonymizeRule(pattern="orders*amount", strategy="mask"),
            AnonymizeRule(pattern="profile.nickname", strategy="mask", mask_value="anon"),
        ],
        entity_field="profile.user.id",
        salt="entity",
    )
    anonymizer = Anonymizer(config)
    records = [
        {
            "profile": {"user": {"id": "u-1"}, "nickname": "bob"},
            "orders": [{"amount": "50"}, {"amount": "60"}],
        }
    ]
    anonymized, report = anonymizer.anonymize_records(records)
    assert anonymized[0]["profile"]["nickname"] == "anon"
    assert anonymized[0]["orders"][0]["amount"] != "50"
    assert len(report.diffs) >= 2
    assert anonymizer._resolve_entity(records[0], 0) == "u-1"
    assert anonymizer._resolve_entity({"profile": {}}, 5) == "record-5"
