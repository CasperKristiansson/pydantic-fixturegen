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
