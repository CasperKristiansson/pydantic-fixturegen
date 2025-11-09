from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic_fixturegen.anonymize.pipeline import (
    AnonymizeBudget,
    AnonymizeConfig,
    Anonymizer,
    AnonymizeReport,
    AnonymizeRule,
    DiffEntry,
    _budget_from_dict,
    _build_rules_from_dicts,
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


def test_faker_strategy_requires_provider() -> None:
    anonymizer = Anonymizer(AnonymizeConfig(rules=[]))
    rule = AnonymizeRule(pattern="email", strategy="faker")
    with pytest.raises(EmitError, match="no provider was supplied"):
        anonymizer._execute_strategy(rule, "addr", "$.email", "record-0")


def test_faker_strategy_requires_known_provider() -> None:
    anonymizer = Anonymizer(AnonymizeConfig(rules=[]))
    rule = AnonymizeRule(pattern="email", strategy="faker", provider="unknown")
    with pytest.raises(EmitError, match="Unknown Faker provider"):
        anonymizer._execute_strategy(rule, "addr", "$.email", "record-0")


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


def test_build_config_merges_profile_and_budget_overrides(tmp_path: Path) -> None:
    rules_file = tmp_path / "budget_rules.json"
    rules_file.write_text(
        json.dumps(
            {
                "anonymize": {
                    "rules": [{"pattern": "*.id", "strategy": "hash"}],
                    "budget": {"max_rule_failures": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    config = build_config_from_rules(
        rules_path=rules_file,
        profile="edge",
        budget_overrides={"max_rule_failures": None},
    )
    assert config.budget.max_rule_failures == 1


def test_load_rules_document_json(tmp_path: Path) -> None:
    rules_file = tmp_path / "ruleset.json"
    payload = {"anonymize": {"rules": [{"pattern": "*.id", "strategy": "hash"}]}}
    rules_file.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_rules_document(rules_file)
    assert loaded["anonymize"]["rules"][0]["strategy"] == "hash"


def test_load_rules_document_yaml(monkeypatch, tmp_path: Path) -> None:
    rules_file = tmp_path / "ruleset.yaml"
    rules_file.write_text("anonymize:\n  rules: []\n", encoding="utf-8")
    fake_yaml = ModuleType("yaml")
    fake_yaml.safe_load = lambda _: {"anonymize": {"rules": []}}
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)
    loaded = load_rules_document(rules_file)
    assert "anonymize" in loaded


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


def test_anonymize_report_to_payload_includes_diffs() -> None:
    report = AnonymizeReport(
        records_processed=2,
        fields_anonymized=3,
        strategy_counts={"mask": 2},
        rule_matches={"pattern": 2},
        rule_failures={"pattern": 1},
        required_rule_misses=0,
        diffs=[
            DiffEntry(
                path="$.user.email",
                before="before@example.com",
                after="anon@example.com",
                strategy="mask",
                record_index=0,
            )
        ],
        doctor_summary={"status": "ok"},
    )

    payload = report.to_payload()

    assert payload["records_processed"] == 2
    assert payload["diffs"][0]["path"] == "$.user.email"
    assert payload["doctor_summary"] == {"status": "ok"}


def test_mask_strategy_handles_empty_values() -> None:
    config = AnonymizeConfig(
        rules=[AnonymizeRule(pattern="profile.secret", strategy="mask")],
        salt="s",
    )
    anonymizer = Anonymizer(config)

    anonymized, _ = anonymizer.anonymize_records([{"profile": {"secret": ""}}])

    assert anonymized[0]["profile"]["secret"] == "*"


def test_rule_failure_budget_enforced_on_exceptions() -> None:
    config = AnonymizeConfig(
        rules=[AnonymizeRule(pattern="profile.name", strategy="unknown")],
        budget=AnonymizeBudget(max_rule_failures=0),
    )
    anonymizer = Anonymizer(config)

    with pytest.raises(EmitError, match="Rule execution failures exceeded budget"):
        anonymizer.anonymize_records([{"profile": {"name": "bob"}}])


def test_load_rules_document_requires_yaml_dependency(monkeypatch, tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("anonymize:\n  rules: []\n", encoding="utf-8")

    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "yaml":
            raise ImportError("yaml missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(EmitError, match="PyYAML is required"):
        load_rules_document(rules_file)


def test_load_rules_document_rejects_non_mapping(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.json"
    rules_file.write_text("[]", encoding="utf-8")

    with pytest.raises(EmitError, match="must contain a mapping"):
        load_rules_document(rules_file)


def test_build_config_from_rules_requires_entries(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"anonymize": {}}), encoding="utf-8")

    with pytest.raises(EmitError, match="No anonymization rules were defined"):
        build_config_from_rules(rules_path=rules_file)


def test_build_rules_from_dicts_validates_entries() -> None:
    with pytest.raises(EmitError, match="must define 'pattern' and 'strategy'"):
        _build_rules_from_dicts([{"pattern": "*.email"}])


def test_budget_from_dict_rejects_negative_values() -> None:
    with pytest.raises(EmitError, match="Budget thresholds must be >= 0."):
        _budget_from_dict({"max_rule_failures": -1})


def test_budget_from_dict_accepts_null_thresholds() -> None:
    budget = _budget_from_dict({"max_rule_failures": None})
    assert budget.max_rule_failures is None
