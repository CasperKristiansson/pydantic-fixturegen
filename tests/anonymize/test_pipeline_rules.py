from pydantic_fixturegen.anonymize.pipeline import AnonymizeRule


def test_anonymize_rule_matches_handles_dotted_paths() -> None:
    rule = AnonymizeRule(pattern="user.email", strategy="hash")

    assert rule.matches("$.user.email")
    assert rule.matches("user.email")
    assert not rule.matches("$.account.email")


def test_anonymize_rule_matches_trims_root_marker() -> None:
    rule = AnonymizeRule(pattern="email", strategy="hash")

    assert rule.matches("$email")
    assert rule.matches("email")
