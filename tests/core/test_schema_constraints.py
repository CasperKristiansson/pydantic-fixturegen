from __future__ import annotations

import dataclasses
import datetime
import uuid
from collections.abc import Callable
from dataclasses import field as dc_field
from decimal import Decimal
from typing import Annotated, Any, Literal, NotRequired, TypedDict, cast

import annotated_types
import email_validator  # noqa: F401
import pytest
from pydantic import AnyUrl, BaseModel, Field, SecretBytes, SecretStr
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.schema import (
    FieldConstraints,
    extract_constraints,
    extract_model_constraints,
    summarize_model_fields,
)


class NumericModel(BaseModel):
    score: Annotated[int, Field(ge=0, le=100)]
    length: Annotated[int, Field(gt=1, lt=10)]
    upper: Annotated[int, Field(le=50)]


class StringModel(BaseModel):
    code: Annotated[str, Field(pattern="^ABC", min_length=3, max_length=5)]
    name: Annotated[str, Field(min_length=2)]


class DecimalModel(BaseModel):
    price: Annotated[Decimal, Field(max_digits=6, decimal_places=2)]


class AdvancedModel(BaseModel):
    quantity: Annotated[int, Field(multiple_of=2, ge=0)]
    short: Annotated[str, annotated_types.MaxLen(4)]
    plain: int


def test_extract_constraints_from_field() -> None:
    field = NumericModel.model_fields["score"]
    constraints = extract_constraints(field)

    assert constraints.ge == 0
    assert constraints.le == 100
    assert constraints.gt is None
    assert constraints.lt is None


def test_extract_model_constraints_handles_numeric_bounds() -> None:
    data = extract_model_constraints(NumericModel)

    assert set(data.keys()) == {"score", "length", "upper"}
    score = data["score"]
    assert score.ge == 0 and score.le == 100

    length = data["length"]
    assert length.gt == 1 and length.lt == 10

    upper = data["upper"]
    assert upper.le == 50


def test_extract_model_constraints_handles_strings() -> None:
    data = extract_model_constraints(StringModel)

    code = data["code"]
    assert code.pattern == "^ABC"
    assert code.min_length == 3
    assert code.max_length == 5

    name = data["name"]
    assert name.min_length == 2
    assert name.max_length is None


def test_extract_model_constraints_handles_decimal_metadata() -> None:
    data = extract_model_constraints(DecimalModel)

    price = data["price"]
    assert price.max_digits == 6
    assert price.decimal_places == 2
    assert price.pattern is None


def test_extract_model_constraints_handles_multiple_of() -> None:
    data = extract_model_constraints(AdvancedModel)

    quantity = data["quantity"]
    assert quantity.multiple_of == 2
    assert quantity.ge == 0

    short = data["short"]
    assert short.max_length == 4
    assert "plain" not in data


def test_field_constraints_has_constraints() -> None:
    empty = FieldConstraints()
    assert empty.has_constraints() is False

    populated = FieldConstraints(ge=1.0)
    assert populated.has_constraints() is True


def test_normalize_decimal_constraints() -> None:
    constraints = FieldConstraints(max_digits=4, decimal_places=6)
    normalize_decimal = cast(
        "Callable[[FieldConstraints], None]",
        schema_module._normalize_decimal_constraints,
    )
    normalize_decimal(constraints)

    assert constraints.max_digits == 4
    assert constraints.decimal_places == 4


def test_internal_numeric_helpers_cover_existing_values() -> None:
    max_value = cast(
        "Callable[[float | None, float | None], float | None]",
        schema_module._max_value,
    )
    min_value = cast(
        "Callable[[float | None, float | None], float | None]",
        schema_module._min_value,
    )
    max_int = cast(
        "Callable[[int | None, int | None], int | None]",
        schema_module._max_int,
    )
    min_int = cast(
        "Callable[[int | None, int | None], int | None]",
        schema_module._min_int,
    )

    assert max_value(10.0, 5) == 10.0
    assert min_value(2.0, 5) == 2.0
    assert max_int(5, 3) == 5
    assert min_int(3, 5) == 3
    assert max_int(5, None) == 5
    assert min_int(5, None) == 5


def test_summarize_field_basic() -> None:
    summary = schema_module.summarize_model_fields(NumericModel)

    assert summary["score"].type == "int"
    assert summary["length"].constraints.gt == 1
    assert summary["upper"].constraints.le == 50


def test_summarize_field_for_list() -> None:
    class CollectionModel(BaseModel):
        tags: Annotated[list[str], Field(min_length=1)]

    summary = schema_module.summarize_model_fields(CollectionModel)
    tags = summary["tags"]
    assert tags.type == "list"
    assert tags.item_type == "string"
    assert tags.constraints.min_length == 1


def test_summarize_field_for_optional() -> None:
    class OptionalModel(BaseModel):
        count: Annotated[int | None, Field(ge=0)]

    summary = schema_module.summarize_model_fields(OptionalModel)
    assert summary["count"].type == "int"
    assert summary["count"].constraints.ge == 0


def test_summarize_field_for_mapping() -> None:
    class MappingModel(BaseModel):
        metadata: dict[str, str]

    summary = schema_module.summarize_model_fields(MappingModel)
    assert summary["metadata"].type == "mapping"


def test_summarize_field_for_uuid_and_datetime() -> None:
    class TemporalModel(BaseModel):
        identifier: uuid.UUID
        created_at: datetime.datetime
        birthday: datetime.date
        wake_up: datetime.time

    summary = schema_module.summarize_model_fields(TemporalModel)
    assert summary["identifier"].type == "uuid"
    assert summary["created_at"].type == "datetime"
    assert summary["birthday"].type == "date"
    assert summary["wake_up"].type == "time"


def test_summarize_field_for_secret_and_url() -> None:
    class SecretsModel(BaseModel):
        password: SecretStr
        token: SecretBytes
        homepage: AnyUrl

    summary = schema_module.summarize_model_fields(SecretsModel)
    assert summary["password"].type == "secret-str"
    assert summary["token"].type == "secret-bytes"
    assert summary["homepage"].type == "url"


def test_summarize_field_for_url_and_any() -> None:
    class MixedModel(BaseModel):
        url: AnyUrl
        misc: Any

    summary = schema_module.summarize_model_fields(MixedModel)
    assert summary["url"].type == "url"
    assert summary["misc"].type == "any"


def test_summarize_field_for_email() -> None:
    from pydantic import EmailStr

    class ContactModel(BaseModel):
        email: EmailStr

    summary = schema_module.summarize_model_fields(ContactModel)
    assert summary["email"].type == "email", f"annotation={summary['email'].annotation!r}"


def test_summarize_field_for_ip_address() -> None:
    from pydantic import IPvAnyAddress

    class NetworkModel(BaseModel):
        host: IPvAnyAddress

    summary = schema_module.summarize_model_fields(NetworkModel)
    assert summary["host"].type == "ip-address"


def test_summarize_field_for_ip_interface_and_network() -> None:
    from pydantic import IPvAnyInterface, IPvAnyNetwork

    class NetModel(BaseModel):
        interface: IPvAnyInterface
        network: IPvAnyNetwork

    summary = schema_module.summarize_model_fields(NetModel)
    assert summary["interface"].type == "ip-interface"
    assert summary["network"].type == "ip-network"


def test_summarize_field_for_nested_model() -> None:
    class Child(BaseModel):
        value: int

    class Parent(BaseModel):
        child: Child

    summary = schema_module.summarize_model_fields(Parent)
    assert summary["child"].type == "model"


def test_summarize_field_for_literal_enum() -> None:
    class LiteralModel(BaseModel):
        status: Literal["a", "b", "c"]

    summary = schema_module.summarize_model_fields(LiteralModel)
    field = summary["status"]
    assert field.type == "enum"
    assert field.enum_values == ["a", "b", "c"]


def test_summarize_model_fields_supports_dataclass_metadata() -> None:
    @dataclasses.dataclass
    class DataClassExample:
        code: Annotated[str, Field(pattern=r"^[A-Z]+$", min_length=2, max_length=5)]
        alias: str = dc_field(default_factory=lambda: "ZZ")

    summaries = summarize_model_fields(DataClassExample)
    assert summaries["alias"].default_factory is not None


def test_summarize_model_fields_supports_typeddict_optionals() -> None:
    class TypedExample(TypedDict):
        required: int
        optional: NotRequired[str]

    summaries = summarize_model_fields(TypedExample)
    optional = summaries["optional"]
    assert optional.is_optional is True
    assert optional.default_value is None


def test_decimal_constraints_normalize_under_limits() -> None:
    class DecimalModel(BaseModel):
        value: Annotated[Decimal, Field(max_digits=2, decimal_places=4)]

    summary = summarize_model_fields(DecimalModel)["value"]
    assert summary.constraints.max_digits == 2
    assert summary.constraints.decimal_places == 2


def test_apply_metadata_with_numeric_bounds() -> None:
    constraints = FieldConstraints()
    schema_module._apply_metadata(constraints, annotated_types.Interval(ge=1, le=5))
    assert constraints.ge == 1 and constraints.le == 5

    class Meta:
        def __init__(self) -> None:
            self.pattern = "^data"
            self.min_length = 2
            self.max_length = 4
            self.max_digits = 6
            self.decimal_places = 8

    info = Meta()
    schema_module._apply_metadata(constraints, info)
    assert constraints.pattern == "^data"
    assert constraints.min_length == 2
    assert constraints.max_length == 4
    schema_module._normalize_decimal_constraints(constraints)
    assert constraints.decimal_places == 6


def test_summarize_model_fields_rejects_unknown_types() -> None:
    class Plain:
        value: int

    with pytest.raises(TypeError):
        summarize_model_fields(Plain)
