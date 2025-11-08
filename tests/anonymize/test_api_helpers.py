from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.anonymize.pipeline import AnonymizeConfig, AnonymizeRule
from pydantic_fixturegen.api.anonymize import anonymize_from_rules, anonymize_payloads


def test_anonymize_payloads_helper() -> None:
    config = AnonymizeConfig(
        rules=[AnonymizeRule(pattern="email", strategy="mask", mask_char="#")],
        salt="api",
    )
    sanitized, report = anonymize_payloads([{"email": "one@example.com"}], config=config)
    assert sanitized[0]["email"] == "#" * len("one@example.com")
    assert report.fields_anonymized == 1


def test_anonymize_from_rules(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.toml"
    rules_file.write_text(
        """
[anonymize]
salt = "api"

  [[anonymize.rules]]
  pattern = "*.email"
  strategy = "mask"
  mask_value = "hidden"
""",
        encoding="utf-8",
    )
    sanitized, report = anonymize_from_rules(
        [{"email": "foo@example.com"}],
        rules_path=rules_file,
        salt="override",
        budget_overrides={"max_rule_failures": 1},
    )
    assert sanitized[0]["email"] == "hidden"
    assert report.fields_anonymized == 1
