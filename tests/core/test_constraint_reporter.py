from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_fixturegen.core import constraint_report as report_mod
from pydantic_fixturegen.core.constraint_report import ConstraintReporter
from pydantic_fixturegen.core.schema import summarize_model_fields


class _User(BaseModel):
    age: int = Field(ge=18)


class _Address(BaseModel):
    city: str = Field(min_length=3)


class _Account(BaseModel):
    addresses: list[_Address]


def test_constraint_reporter_records_failures() -> None:
    reporter = ConstraintReporter()
    summaries = summarize_model_fields(_User)

    reporter.begin_model(_User)
    reporter.record_field_attempt(_User, "age", summaries["age"])
    reporter.record_field_value("age", 5)
    reporter.finish_model(
        _User,
        success=False,
        errors=[
            {
                "loc": ("age",),
                "msg": "Value must be greater than or equal to 18",
                "type": "value_error.number.not_ge",
            }
        ],
    )

    summary = reporter.summary()
    assert summary["total_failures"] == 1
    model_entry = summary["models"][0]
    field_entry = model_entry["fields"][0]
    assert field_entry["name"] == "age"
    assert field_entry["attempts"] == 1
    assert field_entry["successes"] == 0
    assert field_entry["failures"][0]["hint"]


def test_constraint_reporter_merge() -> None:
    reporter_one = ConstraintReporter()
    reporter_two = ConstraintReporter()
    summaries = summarize_model_fields(_User)

    reporter_one.begin_model(_User)
    reporter_one.record_field_attempt(_User, "age", summaries["age"])
    reporter_one.record_field_value("age", 21)
    reporter_one.finish_model(_User, success=True)

    reporter_two.begin_model(_User)
    reporter_two.record_field_attempt(_User, "age", summaries["age"])
    reporter_two.record_field_value("age", 15)
    reporter_two.finish_model(
        _User,
        success=False,
        errors=[
            {
                "loc": ("age",),
                "msg": "value is not enough",
                "type": "value_error.number.not_ge",
            }
        ],
    )

    reporter_one.merge_from(reporter_two)
    summary = reporter_one.summary()
    assert summary["total_models"] == 2
    assert summary["total_failures"] == 1


def test_constraint_reporter_records_nested_failure_value() -> None:
    reporter = ConstraintReporter()
    summaries = summarize_model_fields(_Account)

    reporter.begin_model(_Account)
    reporter.record_field_attempt(_Account, "addresses", summaries["addresses"])
    reporter.record_field_value("addresses", [{"city": "NY"}])
    reporter.finish_model(
        _Account,
        success=False,
        errors=[
            {
                "loc": ("addresses", 0, "city"),
                "msg": "ensure this value has at least 3 characters",
                "type": "value_error.any_str.min_length",
            }
        ],
    )

    assert reporter.has_failures()
    summary = reporter.summary()
    failure = summary["models"][0]["fields"][0]["failures"][0]
    assert failure["location"] == ["addresses", "0", "city"]
    assert failure["value"] == "NY"
    assert "string length" in failure["hint"]


def test_constraint_reporter_merge_prefers_constraints() -> None:
    reporter_base = ConstraintReporter()
    reporter_other = ConstraintReporter()
    summaries = summarize_model_fields(_User)

    reporter_base.begin_model(_User)
    reporter_base.finish_model(
        _User,
        success=False,
        errors=[
            {
                "loc": ("age",),
                "msg": "value too low",
                "type": "value_error.number.not_ge",
            }
        ],
    )

    reporter_other.begin_model(_User)
    reporter_other.record_field_attempt(_User, "age", summaries["age"])
    reporter_other.record_field_value("age", 10)
    reporter_other.finish_model(
        _User,
        success=False,
        errors=[
            {
                "loc": ("age",),
                "msg": "value too low",
                "type": "value_error.number.not_ge",
            }
        ],
    )

    reporter_base.merge_from(reporter_other)
    summary = reporter_base.summary()
    field_entry = summary["models"][0]["fields"][0]
    assert field_entry["constraints"] == {"ge": 18}


def test_hint_for_error_branches() -> None:
    base = report_mod._hint_for_error(None, "field", None, "")
    number = report_mod._hint_for_error("value_error.number.not_ge", "age", None, "")
    string = report_mod._hint_for_error("value_error.any_str.min_length", "name", None, "")
    collection = report_mod._hint_for_error("value_error.list.max_items", "items", None, "")
    type_hint = report_mod._hint_for_error("type_error.enum", "role", None, "")

    assert "overrides" in base
    assert "numeric bounds" in number
    assert "string length" in string
    assert "collection size" in collection
    assert "expected type" in type_hint
