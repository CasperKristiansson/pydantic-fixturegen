from __future__ import annotations

import datetime
import enum
import ipaddress
import uuid
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    IPvAnyAddress,
    IPvAnyInterface,
    IPvAnyNetwork,
    SecretBytes,
    SecretStr,
    model_validator,
)
from pydantic_fixturegen.core.config import ArrayConfig, ConfigError, IdentifierConfig, PathConfig
from pydantic_fixturegen.core.field_policies import FieldPolicy
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.strategies import UnionStrategy

try:  # optional dependency for EmailStr validation
    import email_validator  # noqa: F401
except ImportError:  # pragma: no cover - dependency missing
    EMAIL_VALIDATOR_AVAILABLE = False
else:  # pragma: no cover - dependency present
    EMAIL_VALIDATOR_AVAILABLE = True

_PaymentCardNumber = None
with suppress(ImportError):  # optional dependency for PaymentCardNumber type
    from pydantic_extra_types.payment import PaymentCardNumber as _PaymentCardNumber

PAYMENT_CARD_AVAILABLE = _PaymentCardNumber is not None


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str


class User(BaseModel):
    name: str = Field(pattern="^User", min_length=5)
    age: int
    nickname: str | None
    address: Address
    tags: list[str]
    role: Color
    preference: int | str
    teammates: list[Address]
    contacts: dict[str, Address]


class PathExample(BaseModel):
    artifact: Path
    backup: Path


IdentifierExample: type[BaseModel] | None = None
if EMAIL_VALIDATOR_AVAILABLE and PAYMENT_CARD_AVAILABLE:

    class _IdentifierExample(BaseModel):
        email: EmailStr
        url: AnyUrl
        uuid_value: uuid.UUID
        payment_card: _PaymentCardNumber  # type: ignore[valid-type]
        secret_text: SecretStr
        secret_token: SecretBytes
        ip_address: IPvAnyAddress
        ip_interface: IPvAnyInterface
        ip_network: IPvAnyNetwork
        amount: Decimal = Field(
            max_digits=6,
            decimal_places=2,
            ge=Decimal("1.00"),
            le=Decimal("9.99"),
        )

    IdentifierExample = _IdentifierExample


def test_generate_user_instance() -> None:
    generator = InstanceGenerator(config=GenerationConfig(seed=42))
    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert user.address and isinstance(user.address, Address)
    assert user.name.startswith("User")
    assert user.role in (Color.RED, Color.BLUE)
    assert user.preference is not None


def test_optional_none_probability() -> None:
    config = GenerationConfig(seed=1, optional_p_none=1.0)
    generator = InstanceGenerator(config=config)
    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert user.nickname is None


class Node(BaseModel):
    name: str
    child: Node | None


Node.model_rebuild()


def test_recursion_guard_depth() -> None:
    config = GenerationConfig(seed=7, max_depth=1)
    generator = InstanceGenerator(config=config)
    node = generator.generate_one(Node)
    assert isinstance(node, Node)
    assert node.child is None


def test_object_budget_limits() -> None:
    config = GenerationConfig(seed=3, max_objects=1)
    generator = InstanceGenerator(config=config)
    # Address + User requires more than 1 object, expect None
    assert generator.generate_one(User) is None


def test_union_random_policy() -> None:
    config = GenerationConfig(seed=5, union_policy="random")
    generator = InstanceGenerator(config=config)

    user = generator.generate_one(User)
    assert isinstance(user, User)
    assert isinstance(user.preference, int | str)
    assert isinstance(user.teammates, list)
    assert all(isinstance(member, Address) for member in user.teammates)
    assert isinstance(user.contacts, dict)
    assert all(isinstance(addr, Address) for addr in user.contacts.values())


@dataclass
class Profile:
    username: str
    active: bool


class Account(BaseModel):
    user: User
    profile: Profile


def test_dataclass_field_generation() -> None:
    generator = InstanceGenerator(config=GenerationConfig(seed=11))
    account = generator.generate_one(Account)
    assert account is not None
    assert isinstance(account, Account)
    assert isinstance(account.profile, Profile)
    assert isinstance(account.user.address, Address)


class OptionalItem(BaseModel):
    maybe: str | None


class PolicyWrapper(BaseModel):
    nested: OptionalItem


def test_field_policy_overrides_p_none() -> None:
    pattern = f"{OptionalItem.__module__}.{OptionalItem.__qualname__}.maybe"
    policy = FieldPolicy(pattern=pattern, options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=1,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    instance = generator.generate_one(OptionalItem)
    assert instance is not None
    assert isinstance(instance, OptionalItem)
    assert instance.maybe is not None


def test_field_policy_conflict_raises() -> None:
    pattern1 = f"{OptionalItem.__module__}.*.maybe"
    pattern2 = f"{OptionalItem.__module__}.{OptionalItem.__qualname__}.maybe"
    policies = (
        FieldPolicy(pattern=pattern1, options={"p_none": 0.0}, index=0),
        FieldPolicy(pattern=pattern2, options={"p_none": 1.0}, index=1),
    )
    generator = InstanceGenerator(config=GenerationConfig(field_policies=policies))

    with pytest.raises(ConfigError):
        generator.generate_one(OptionalItem)


def test_field_policy_matches_model_name_alias() -> None:
    policy = FieldPolicy(pattern="OptionalItem.maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=123,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_matches_field_path_alias() -> None:
    policy = FieldPolicy(pattern="PolicyWrapper.nested.maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=321,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_matches_field_name_alias() -> None:
    policy = FieldPolicy(pattern="maybe", options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=11,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_regex_pattern_matches() -> None:
    policy = FieldPolicy(
        pattern=f"re:.*{OptionalItem.__qualname__}\\.maybe$",
        options={"p_none": 0.0},
        index=0,
    )
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=17,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    wrapper = generator.generate_one(PolicyWrapper)
    assert wrapper is not None
    assert isinstance(wrapper, PolicyWrapper)
    assert wrapper.nested.maybe is not None


def test_field_policy_updates_union_strategy() -> None:
    policy = FieldPolicy(
        pattern=f"{User.__qualname__}.preference",
        options={"union_policy": "random", "p_none": 0.0},
        index=0,
    )
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=23,
            field_policies=(policy,),
        )
    )

    strategies = generator._get_model_strategies(User)
    union_strategy = strategies["preference"]
    assert isinstance(union_strategy, UnionStrategy)

    path_stack = getattr(generator, "_path_stack")  # noqa: B009
    make_path_entry = getattr(generator, "_make_path_entry")  # noqa: B009
    path_stack.append(make_path_entry(User, None))
    try:
        apply_field_policies = getattr(generator, "_apply_field_policies")  # noqa: B009
        apply_field_policies("preference", union_strategy)
    finally:
        path_stack.pop()

    assert union_strategy.policy == "random"
    assert all(choice.p_none == 0.0 for choice in union_strategy.choices)


def test_field_policy_applies_via_model_alias() -> None:
    class OptionalModel(BaseModel):
        maybe: str | None = None

    policy = FieldPolicy(pattern=OptionalModel.__qualname__, options={"p_none": 0.0}, index=0)
    generator = InstanceGenerator(
        config=GenerationConfig(
            seed=17,
            optional_p_none=1.0,
            field_policies=(policy,),
        )
    )

    instance = generator.generate_one(OptionalModel)
    assert instance is not None
    assert instance.maybe is not None


class TemporalModel(BaseModel):
    created_at: datetime.datetime
    birthday: datetime.date
    alarm: datetime.time


class LocaleModel(BaseModel):
    city: str


def _capture_locale_generator(
    pattern: str, locale_value: str
) -> tuple[InstanceGenerator, dict[str, list[str]]]:
    registry = ProviderRegistry()
    captured: dict[str, list[str]] = {}

    def locale_provider(summary, *, faker, random_generator, **kwargs):  # type: ignore[override]
        locales = getattr(faker, "locales", [])
        captured["locale"] = locales
        return locales[0] if locales else "unknown"

    registry.register("string", locale_provider)
    policy = FieldPolicy(pattern=pattern, options={"locale": locale_value}, index=0)
    config = GenerationConfig(seed=456, locale_policies=(policy,))
    generator = InstanceGenerator(registry=registry, config=config)
    return generator, captured


def test_locale_policy_applies_to_field() -> None:
    generator, captured = _capture_locale_generator("*LocaleModel.city", "fr_FR")

    instance = generator.generate_one(LocaleModel)
    assert instance is not None
    assert instance.city == "fr_FR"
    assert captured.get("locale") == ["fr_FR"]


@pytest.mark.parametrize(
    "pattern",
    [
        str(f"{LocaleModel.__module__}.{LocaleModel.__qualname__}"),
        str(LocaleModel.__qualname__),
    ],
)
def test_locale_policy_applies_to_model_alias(pattern: str) -> None:
    generator, captured = _capture_locale_generator(pattern, "de_DE")

    instance = generator.generate_one(LocaleModel)
    assert instance is not None
    assert instance.city == "de_DE"
    assert captured.get("locale") == ["de_DE"]


def test_numpy_array_generation() -> None:
    np = pytest.importorskip("numpy")
    from numpy.typing import NDArray

    class ArrayModel(BaseModel):
        values: np.ndarray
        model_config = ConfigDict(arbitrary_types_allowed=True)

    class TypedModel(BaseModel):
        values: NDArray[np.int32]
        model_config = ConfigDict(arbitrary_types_allowed=True)

    array_config = ArrayConfig(
        max_ndim=2,
        max_side=3,
        max_elements=9,
        dtypes=("float32", "int32"),
    )

    generator = InstanceGenerator(config=GenerationConfig(seed=321, arrays=array_config))
    array_instance = generator.generate_one(ArrayModel)
    assert array_instance is not None
    arr = array_instance.values
    assert isinstance(arr, np.ndarray)
    assert arr.size <= array_config.max_elements
    assert arr.ndim <= array_config.max_ndim
    assert arr.dtype.name in array_config.dtypes

    typed_generator = InstanceGenerator(config=GenerationConfig(seed=654, arrays=array_config))
    typed_instance = typed_generator.generate_one(TypedModel)
    assert typed_instance is not None
    typed_arr = typed_instance.values
    assert isinstance(typed_arr, np.ndarray)
    assert typed_arr.dtype.name in array_config.dtypes


def test_time_anchor_produces_deterministic_temporal_values() -> None:
    anchor = datetime.datetime(2025, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc)
    generator = InstanceGenerator(config=GenerationConfig(seed=123, time_anchor=anchor))

    instance = generator.generate_one(TemporalModel)
    assert instance is not None
    assert isinstance(instance, TemporalModel)
    assert instance.created_at == anchor
    assert instance.birthday == anchor.date()
    # allow either naive or aware time depending on anchor tzinfo
    expected_time = anchor.timetz() if anchor.tzinfo else anchor.time()
    assert instance.alarm.isoformat() == expected_time.isoformat()


@pytest.mark.skipif(
    not (EMAIL_VALIDATOR_AVAILABLE and PAYMENT_CARD_AVAILABLE),
    reason="email-validator or payment extra not installed",
)
def test_identifier_generation_is_deterministic() -> None:
    assert IdentifierExample is not None
    first_generator = InstanceGenerator(config=GenerationConfig(seed=2024))
    first = first_generator.generate_one(IdentifierExample)

    second_generator = InstanceGenerator(config=GenerationConfig(seed=2024))
    second = second_generator.generate_one(IdentifierExample)

    assert first is not None and second is not None
    assert first.email == second.email
    assert first.url == second.url
    assert str(first.payment_card) == str(second.payment_card)
    assert first.uuid_value == second.uuid_value
    assert first.secret_text.get_secret_value() == second.secret_text.get_secret_value()
    assert first.secret_token.get_secret_value() == second.secret_token.get_secret_value()
    assert str(first.ip_address) == str(second.ip_address)
    assert str(first.ip_interface) == str(second.ip_interface)
    assert str(first.ip_network) == str(second.ip_network)
    assert first.amount == second.amount


@pytest.mark.skipif(
    not (EMAIL_VALIDATOR_AVAILABLE and PAYMENT_CARD_AVAILABLE),
    reason="email-validator or payment extra not installed",
)
def test_identifier_generation_respects_configuration() -> None:
    assert IdentifierExample is not None
    identifier_config = IdentifierConfig(
        secret_str_length=22,
        secret_bytes_length=7,
        url_schemes=("ftp",),
        url_include_path=False,
        uuid_version=1,
    )
    generator = InstanceGenerator(config=GenerationConfig(seed=99, identifiers=identifier_config))
    result = generator.generate_one(IdentifierExample)

    assert result is not None
    url_value = str(result.url)
    assert url_value.startswith("ftp://")
    assert result.url.path in ("", "/")
    assert result.uuid_value.version == 1
    assert len(result.secret_text.get_secret_value()) == 22
    assert len(result.secret_token.get_secret_value()) == 7
    assert isinstance(result.ip_address, ipaddress.IPv4Address | ipaddress.IPv6Address)
    assert isinstance(result.ip_interface, ipaddress.IPv4Interface | ipaddress.IPv6Interface)
    assert isinstance(result.ip_network, ipaddress.IPv4Network | ipaddress.IPv6Network)
    assert result.amount.as_tuple().exponent == -2


class FailOnceModel(BaseModel):
    value: int
    attempts: ClassVar[int] = 0

    @model_validator(mode="after")
    def fail_first(self) -> FailOnceModel:
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise ValueError("try again")
        return self


class AlwaysInvalidModel(BaseModel):
    value: int

    @model_validator(mode="after")
    def always_fail(self) -> AlwaysInvalidModel:
        raise ValueError("never valid")


def test_validator_retry_disabled_returns_none() -> None:
    FailOnceModel.attempts = 0
    generator = InstanceGenerator(config=GenerationConfig(seed=1, respect_validators=False))

    assert generator.generate_one(FailOnceModel) is None
    failure = generator.validator_failure_details
    assert failure is None or failure["attempt"] == 1


def test_validator_retry_enabled_recovers_after_failure() -> None:
    FailOnceModel.attempts = 0
    generator = InstanceGenerator(
        config=GenerationConfig(seed=2, respect_validators=True, validator_max_retries=3)
    )

    instance = generator.generate_one(FailOnceModel)
    assert isinstance(instance, FailOnceModel)
    assert FailOnceModel.attempts == 2


def test_validator_failure_details_capture_attempts() -> None:
    generator = InstanceGenerator(
        config=GenerationConfig(seed=5, respect_validators=True, validator_max_retries=1)
    )

    assert generator.generate_one(AlwaysInvalidModel) is None
    failure = generator.validator_failure_details
    assert failure is not None
    assert failure["model"].endswith("AlwaysInvalidModel")
    assert failure["attempt"] == 2
    assert failure["max_attempts"] == 2
    assert "values" in failure and "value" in failure["values"]


def test_path_generation_respects_default_os() -> None:
    config = GenerationConfig(seed=321, paths=PathConfig(default_os="windows"))
    generator = InstanceGenerator(config=config)

    instance = generator.generate_one(PathExample)
    assert instance is not None
    assert "\\" in str(instance.artifact)
    assert ":" in str(instance.artifact)


def test_path_generation_supports_model_overrides() -> None:
    pattern = f"{PathExample.__module__}.{PathExample.__qualname__}"
    path_config = PathConfig(default_os="posix", model_targets=((pattern, "mac"),))
    generator = InstanceGenerator(config=GenerationConfig(seed=654, paths=path_config))

    instance = generator.generate_one(PathExample)
    assert instance is not None
    rendered = str(instance.artifact)
    assert rendered.startswith(("/Users", "/Applications", "/Volumes"))
