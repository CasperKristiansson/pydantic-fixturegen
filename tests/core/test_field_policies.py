from __future__ import annotations

import pytest
from pydantic_fixturegen.core.field_policies import (
    FieldPolicy,
    FieldPolicyConflictError,
    FieldPolicySet,
)


def test_field_policy_resolve_deduplicated_aliases() -> None:
    policy = FieldPolicy(pattern="*.field", options={"p_none": 0.25}, index=0)
    policies = FieldPolicySet((policy,))

    result = policies.resolve(
        "app.Model.field",
        aliases=("Model.field", "Model.field", "field"),
    )

    assert result == {"p_none": 0.25}


def test_field_policy_conflict_raises_with_alias() -> None:
    policies = FieldPolicySet(
        (
            FieldPolicy(pattern="*.field", options={"p_none": 0.1}, index=0),
            FieldPolicy(pattern="Model.*", options={"p_none": 0.2}, index=1),
        )
    )

    with pytest.raises(FieldPolicyConflictError) as exc:
        policies.resolve("pkg.Model.field", aliases=("Model.field",))

    assert "Model.*" in str(exc.value)


def test_field_policy_requires_pattern() -> None:
    with pytest.raises(ValueError):
        FieldPolicy(pattern="  ", options={}, index=0)


def test_field_policy_regex_matching() -> None:
    policy = FieldPolicy(pattern=r"re:^Model\.[A-Za-z]+$", options={"p_none": 0.5}, index=0)
    assert policy.matches("Model.field")
    assert not policy.matches("Other.field")
    assert policy.specificity[0] == 1000


def test_field_policy_set_ignores_none_options() -> None:
    policy = FieldPolicy(pattern="Model.field", options={"p_none": 0.1, "alias": None}, index=0)
    result = FieldPolicySet((policy,)).resolve("Model.field")
    assert result == {"p_none": 0.1}


def test_field_policy_set_iterable_sorted() -> None:
    policies = (
        FieldPolicy(pattern="Model.*", options={"p_none": 0.2}, index=1),
        FieldPolicy(pattern="*.field", options={"p_none": 0.3}, index=0),
    )
    ordered = FieldPolicySet(policies).iterable()
    assert list(ordered)[0].pattern == "*.field"
