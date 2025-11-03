from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_fixturegen.core.constraint_report import ConstraintReporter
from pydantic_fixturegen.core.schema import summarize_model_fields


class _User(BaseModel):
    age: int = Field(ge=18)


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
