from __future__ import annotations

import datetime
import decimal
import random
import uuid
from typing import Any

import pytest
from faker import Faker
from pydantic import BaseModel, SecretBytes, SecretStr
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.config import IdentifierConfig
from pydantic_fixturegen.core.providers import (
    ProviderRef,
    ProviderRegistry,
    create_default_registry,
)
from pydantic_fixturegen.core.providers import strings as strings_module
from pydantic_fixturegen.core.providers.collections import register_collection_providers
from pydantic_fixturegen.core.providers.identifiers import register_identifier_providers
from pydantic_fixturegen.core.providers.numbers import register_numeric_providers
from pydantic_fixturegen.core.providers.strings import register_string_providers
from pydantic_fixturegen.core.providers.temporal import register_temporal_providers
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.plugins.hookspecs import hookimpl


def test_register_and_lookup_provider() -> None:
    registry = ProviderRegistry()

    def provider(_: Any) -> str:
        return "value"

    ref = registry.register("string", provider, name="basic")

    assert isinstance(ref, ProviderRef)
    fetched = registry.get("string")
    assert fetched is ref
    assert fetched.func(None) == "value"

    with pytest.raises(ValueError):
        registry.register("string", provider)

    registry.unregister("string")
    assert registry.get("string") is None


def test_register_with_format_and_override() -> None:
    registry = ProviderRegistry()

    registry.register("string", lambda _: "plain")
    with_format = registry.register("string", lambda _: "email", format="email")

    assert registry.get("string", "email") is with_format
    assert registry.get("string") is not None

    def replacement(_: Any) -> str:
        return "override"

    registry.register("string", replacement, override=True)
    override_provider = registry.get("string")
    assert override_provider is not None
    assert override_provider.func(None) == "override"
    assert list(registry.available())
    registry.clear()
    assert list(registry.available()) == []


def test_register_plugin_invokes_hook() -> None:
    registry = ProviderRegistry()

    class Plugin:
        @hookimpl
        def pfg_register_providers(self, registry: ProviderRegistry) -> None:
            registry.register("int", lambda _: 42, name="answer")

    registry.register_plugin(Plugin())

    provider = registry.get("int")
    assert provider is not None
    assert provider.func(None) == 42


def test_load_entrypoint_plugins_handles_missing_group(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ProviderRegistry()

    class DummyPlugin:
        @hookimpl
        def pfg_register_providers(self, registry: ProviderRegistry) -> None:
            registry.register("bool", lambda _: True)

    class DummyEntryPoint:
        def load(self) -> object:
            return DummyPlugin()

    class DummyEntryPoints:
        @staticmethod
        def select(group: str) -> list[DummyEntryPoint]:
            assert group == "pydantic_fixturegen"
            return [DummyEntryPoint()]

    monkeypatch.setattr("importlib.metadata.entry_points", lambda: DummyEntryPoints())

    registry.load_entrypoint_plugins(force=True)
    bool_provider = registry.get("bool")
    assert bool_provider is not None
    assert bool_provider.func(None) is True


class SecretsExample(BaseModel):
    token: SecretBytes
    password: SecretStr


def test_string_provider_respects_constraints() -> None:
    registry = ProviderRegistry()
    register_string_providers(registry)

    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=5, pattern="^FIX"),
        format=None,
    )
    provider = registry.get("string")
    assert provider is not None

    faker = Faker(seed=1)
    value = provider.func(summary=summary, faker=faker)
    assert isinstance(value, str)
    assert value.startswith("FIX")
    assert len(value) >= 5


def test_string_provider_formats() -> None:
    registry = ProviderRegistry()
    register_string_providers(registry)
    provider = registry.get("string")
    assert provider is not None

    faker = Faker(seed=2)

    plain_summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=2, max_length=3),
        format=None,
    )
    plain_value = provider.func(
        summary=plain_summary,
        faker=faker,
        random_generator=random.Random(1),
    )
    assert 2 <= len(plain_value) <= 3


def test_identifier_provider_formats() -> None:
    registry = ProviderRegistry()
    register_identifier_providers(registry)
    provider = registry.get("email")
    assert provider is not None

    faker = Faker(seed=3)
    email_value = provider.func(
        summary=FieldSummary(type="email", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(1),
    )
    assert "@" in email_value

    card_provider = registry.get("payment-card")
    assert card_provider is not None
    card_value = card_provider.func(
        summary=FieldSummary(type="payment-card", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(2),
    )
    assert isinstance(card_value, str) and len(card_value) > 0

    url_provider = registry.get("url")
    assert url_provider is not None
    url_value = url_provider.func(
        summary=FieldSummary(type="url", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(3),
    )
    assert url_value.startswith("http")

    secret_str_provider = registry.get("secret-str")
    assert secret_str_provider is not None
    secret_str = secret_str_provider.func(
        summary=FieldSummary(type="secret-str", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(4),
    )
    assert isinstance(secret_str, SecretStr)
    assert len(secret_str.get_secret_value()) == IdentifierConfig().secret_str_length

    secret_bytes_provider = registry.get("secret-bytes")
    assert secret_bytes_provider is not None
    secret_bytes = secret_bytes_provider.func(
        summary=FieldSummary(type="secret-bytes", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(5),
    )
    assert isinstance(secret_bytes, SecretBytes)
    assert len(secret_bytes.get_secret_value()) > 0
    assert len(secret_bytes.get_secret_value()) == IdentifierConfig().secret_bytes_length

    ip_provider = registry.get("ip-address")
    assert ip_provider is not None
    ip_value = ip_provider.func(
        summary=FieldSummary(type="ip-address", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(6),
    )
    assert isinstance(ip_value, str)

    ip_interface_provider = registry.get("ip-interface")
    assert ip_interface_provider is not None
    ip_interface = ip_interface_provider.func(
        summary=FieldSummary(type="ip-interface", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(7),
    )
    assert "/" in ip_interface

    ip_network_provider = registry.get("ip-network")
    assert ip_network_provider is not None
    ip_network = ip_network_provider.func(
        summary=FieldSummary(type="ip-network", constraints=FieldConstraints()),
        faker=faker,
        random_generator=random.Random(8),
    )
    assert "/" in ip_network


def test_identifier_provider_respects_configuration() -> None:
    registry = ProviderRegistry()
    register_identifier_providers(registry)

    identifier_config = IdentifierConfig(
        secret_str_length=8,
        secret_bytes_length=10,
        url_schemes=("ftp",),
        url_include_path=False,
        uuid_version=1,
    )

    secret_summary = FieldSummary(type="secret-str", constraints=FieldConstraints())
    secret = registry.get("secret-str")
    assert secret is not None
    secret_value = secret.func(
        summary=secret_summary,
        faker=Faker(seed=2),
        random_generator=random.Random(9),
        identifier_config=identifier_config,
    )
    assert isinstance(secret_value, SecretStr)
    assert len(secret_value.get_secret_value()) == 8

    secret_bytes = registry.get("secret-bytes")
    assert secret_bytes is not None
    token = secret_bytes.func(
        summary=FieldSummary(type="secret-bytes", constraints=FieldConstraints()),
        faker=Faker(seed=3),
        random_generator=random.Random(10),
        identifier_config=identifier_config,
    )
    assert isinstance(token, SecretBytes)
    assert len(token.get_secret_value()) == 10

    url_provider = registry.get("url")
    assert url_provider is not None
    url_value = url_provider.func(
        summary=FieldSummary(type="url", constraints=FieldConstraints()),
        faker=Faker(seed=4),
        random_generator=random.Random(11),
        identifier_config=identifier_config,
    )
    assert url_value.startswith("ftp://")
    assert "/" not in url_value[len("ftp://") :]

    uuid_provider = registry.get("uuid")
    assert uuid_provider is not None
    uuid_value = uuid_provider.func(
        summary=FieldSummary(type="uuid", constraints=FieldConstraints()),
        faker=Faker(seed=5),
        random_generator=random.Random(12),
        identifier_config=identifier_config,
    )
    assert uuid_value.version == 1


def test_identifier_provider_requires_random_generator() -> None:
    registry = ProviderRegistry()
    register_identifier_providers(registry)
    provider = registry.get("email")
    assert provider is not None

    with pytest.raises(RuntimeError):
        provider.func(
            summary=FieldSummary(type="email", constraints=FieldConstraints()),
            faker=Faker(seed=6),
        )


def test_numeric_provider_respects_bounds() -> None:
    registry = ProviderRegistry()
    register_numeric_providers(registry)
    provider = registry.get("int")
    assert provider is not None

    summary = FieldSummary(
        type="int",
        constraints=FieldConstraints(ge=5, le=5),
        format=None,
    )
    value = provider.func(summary=summary, random_generator=random.Random(0))
    assert value == 5

    float_summary = FieldSummary(
        type="float",
        constraints=FieldConstraints(ge=1.5, le=2.5),
        format=None,
    )
    float_provider = registry.get("float")
    assert float_provider is not None
    float_value = float_provider.func(
        summary=float_summary,
        random_generator=random.Random(1),
    )
    assert 1.5 <= float_value <= 2.5

    decimal_summary = FieldSummary(
        type="decimal",
        constraints=FieldConstraints(
            ge=1.10,
            le=1.20,
            decimal_places=2,
        ),
        format=None,
    )
    decimal_provider = registry.get("decimal")
    assert decimal_provider is not None
    decimal_value = decimal_provider.func(
        summary=decimal_summary,
        random_generator=random.Random(2),
    )
    assert decimal.Decimal("1.10") <= decimal_value <= decimal.Decimal("1.20")
    assert decimal_value.as_tuple().exponent == -2

    bool_provider = registry.get("bool")
    assert bool_provider is not None
    bool_value = bool_provider.func(
        summary=FieldSummary(type="bool", constraints=FieldConstraints()),
        random_generator=random.Random(3),
    )
    assert isinstance(bool_value, bool)


def test_collection_provider_generates_items() -> None:
    registry = ProviderRegistry()
    register_collection_providers(registry)

    summary = FieldSummary(
        type="list",
        constraints=FieldConstraints(min_length=2, max_length=4),
        format=None,
        item_type="int",
    )
    list_provider = registry.get("list")
    assert list_provider is not None
    values = list_provider.func(
        summary=summary,
        faker=Faker(seed=10),
        random_generator=random.Random(2),
    )
    assert 2 <= len(values) <= 4
    assert all(isinstance(v, int) for v in values)

    set_summary = FieldSummary(
        type="set",
        constraints=FieldConstraints(min_length=1, max_length=2),
        format=None,
        item_type="float",
    )
    set_provider = registry.get("set")
    assert set_provider is not None
    set_values = set_provider.func(
        summary=set_summary,
        faker=Faker(seed=11),
        random_generator=random.Random(4),
    )
    assert isinstance(set_values, set)
    assert 1 <= len(set_values) <= 2

    tuple_summary = FieldSummary(
        type="tuple",
        constraints=FieldConstraints(min_length=1, max_length=1),
        format=None,
        item_type="string",
    )
    tuple_provider = registry.get("tuple")
    assert tuple_provider is not None
    tuple_value = tuple_provider.func(
        summary=tuple_summary,
        faker=Faker(seed=12),
        random_generator=random.Random(5),
    )
    assert isinstance(tuple_value, tuple)
    assert len(tuple_value) == 1

    mapping_summary = FieldSummary(
        type="mapping",
        constraints=FieldConstraints(min_length=1, max_length=1),
        format=None,
        item_type="int",
    )
    mapping_provider = registry.get("mapping")
    assert mapping_provider is not None
    mapping_value = mapping_provider.func(
        summary=mapping_summary,
        faker=Faker(seed=13),
        random_generator=random.Random(6),
    )
    assert isinstance(mapping_value, dict)
    assert len(mapping_value) == 1
    assert all(isinstance(v, int) for v in mapping_value.values())


def test_default_registry_includes_providers() -> None:
    registry = create_default_registry(load_plugins=False)
    assert registry.get("string") is not None
    assert registry.get("int") is not None
    assert registry.get("list") is not None
    assert registry.get("datetime") is not None
    assert registry.get("email") is not None


def test_temporal_provider_outputs_types() -> None:
    registry = ProviderRegistry()
    from pydantic_fixturegen.core.providers.temporal import register_temporal_providers

    register_temporal_providers(registry)
    faker = Faker(seed=11)

    datetime_provider = registry.get("datetime")
    assert datetime_provider is not None
    dt = datetime_provider.func(
        summary=FieldSummary(type="datetime", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(dt, datetime.datetime)

    date_provider = registry.get("date")
    assert date_provider is not None
    d = date_provider.func(
        summary=FieldSummary(type="date", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(d, datetime.date)

    time_provider = registry.get("time")
    assert time_provider is not None
    t = time_provider.func(
        summary=FieldSummary(type="time", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(t, datetime.time)


def test_string_provider_secret_bytes() -> None:
    registry = ProviderRegistry()
    register_string_providers(registry)
    provider = registry.get("string")
    assert provider is not None

    summary = schema_module.summarize_model_fields(SecretsExample)
    value = provider.func(summary=summary["token"], faker=Faker(seed=3))
    assert isinstance(value, bytes)
    assert len(value) > 0

    password = provider.func(summary=summary["password"], faker=Faker(seed=4))
    assert isinstance(password, str)
    assert len(password) > 0


def test_string_provider_temporal_and_uuid() -> None:
    registry = ProviderRegistry()
    register_identifier_providers(registry)
    register_temporal_providers(registry)

    class TemporalModel(BaseModel):
        identifier: uuid.UUID
        created_at: datetime.datetime
        birthday: datetime.date
        wake_up: datetime.time

    summary = schema_module.summarize_model_fields(TemporalModel)
    faker = Faker(seed=5)

    uuid_provider = registry.get("uuid")
    assert uuid_provider is not None
    identifier = uuid_provider.func(
        summary=summary["identifier"],
        faker=faker,
        random_generator=random.Random(13),
    )
    assert isinstance(identifier, uuid.UUID)

    datetime_provider = registry.get("datetime")
    assert datetime_provider is not None
    created = datetime_provider.func(summary=summary["created_at"], faker=faker)
    assert isinstance(created, datetime.datetime)

    birthday_provider = registry.get("date")
    assert birthday_provider is not None
    birthday = birthday_provider.func(summary=summary["birthday"], faker=faker)
    assert isinstance(birthday, datetime.date)

    wake_provider = registry.get("time")
    assert wake_provider is not None
    wake = wake_provider.func(summary=summary["wake_up"], faker=faker)
    assert isinstance(wake, datetime.time)


def test_string_provider_regex_padding(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ProviderRegistry()
    register_string_providers(registry)
    provider = registry.get("string")
    assert provider is not None

    class DummyRstr:
        @staticmethod
        def xeger(pattern: str) -> str:
            return "ABCDEFG"  # intentionally longer than allowed

    monkeypatch.setattr(strings_module, "rstr", DummyRstr())

    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=5, max_length=6, pattern="^AB"),
        format=None,
    )
    value = provider.func(summary=summary, faker=Faker(seed=7))
    assert value.startswith("AB")
    assert len(value) == summary.constraints.max_length

    monkeypatch.setattr(strings_module, "rstr", None)

    empty_pattern_summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=4, max_length=5, pattern="^$"),
        format=None,
    )
    generated = provider.func(summary=empty_pattern_summary, faker=Faker(seed=8))
    assert 4 <= len(generated) <= 5

    adjusted_summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=7, max_length=5),
        format=None,
    )
    adjusted_value = provider.func(summary=adjusted_summary, faker=Faker(seed=9))
    assert len(adjusted_value) == 5


def test_temporal_provider_uses_anchor() -> None:
    registry = ProviderRegistry()
    register_temporal_providers(registry)

    anchor = datetime.datetime(2025, 1, 1, 12, 30, 45, tzinfo=datetime.timezone.utc)
    faker = Faker(seed=10)

    datetime_summary = FieldSummary(type="datetime", constraints=FieldConstraints())
    datetime_provider = registry.get("datetime")
    assert datetime_provider is not None
    datetime_value = datetime_provider.func(
        summary=datetime_summary,
        faker=faker,
        time_anchor=anchor,
    )
    assert datetime_value == anchor

    date_summary = FieldSummary(type="date", constraints=FieldConstraints())
    date_provider = registry.get("date")
    assert date_provider is not None
    date_value = date_provider.func(
        summary=date_summary,
        faker=faker,
        time_anchor=anchor,
    )
    assert date_value == anchor.date()

    time_summary = FieldSummary(type="time", constraints=FieldConstraints())
    time_provider = registry.get("time")
    assert time_provider is not None
    time_value = time_provider.func(summary=time_summary, faker=faker, time_anchor=anchor)
    assert time_value.isoformat() == anchor.timetz().isoformat()
