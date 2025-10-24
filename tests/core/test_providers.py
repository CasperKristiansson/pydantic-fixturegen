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
    assert registry.get("string").func(None) == "override"
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


def test_load_entrypoint_plugins_handles_missing_group(monkeypatch) -> None:
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
        def select(group: str):
            assert group == "pydantic_fixturegen"
            return [DummyEntryPoint()]

    monkeypatch.setattr("importlib.metadata.entry_points", lambda: DummyEntryPoints())

    registry.load_entrypoint_plugins(force=True)
    assert registry.get("bool").func(None) is True


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
    )
    assert "@" in email_value

    card_value = registry.get("payment-card").func(
        summary=FieldSummary(type="payment-card", constraints=FieldConstraints()),
        faker=faker,
    )
    assert isinstance(card_value, str) and len(card_value) > 0

    url_value = registry.get("url").func(
        summary=FieldSummary(type="url", constraints=FieldConstraints()),
        faker=faker,
    )
    assert url_value.startswith("http")

    secret_str = registry.get("secret-str").func(
        summary=FieldSummary(type="secret-str", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(secret_str, SecretStr)

    secret_bytes = registry.get("secret-bytes").func(
        summary=FieldSummary(type="secret-bytes", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(secret_bytes, SecretBytes)
    assert len(secret_bytes.get_secret_value()) > 0

    ip_value = registry.get("ip-address").func(
        summary=FieldSummary(type="ip-address", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(ip_value, str)

    ip_interface = registry.get("ip-interface").func(
        summary=FieldSummary(type="ip-interface", constraints=FieldConstraints()), faker=faker
    )
    assert "/" in ip_interface

    ip_network = registry.get("ip-network").func(
        summary=FieldSummary(type="ip-network", constraints=FieldConstraints()), faker=faker
    )
    assert "/" in ip_network


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
    float_value = registry.get("float").func(
        summary=float_summary,
        random_generator=random.Random(1),
    )
    assert 1.5 <= float_value <= 2.5

    decimal_summary = FieldSummary(
        type="decimal",
        constraints=FieldConstraints(
            ge=decimal.Decimal("1.10"),
            le=decimal.Decimal("1.20"),
            decimal_places=2,
        ),
        format=None,
    )
    decimal_value = registry.get("decimal").func(
        summary=decimal_summary,
        random_generator=random.Random(2),
    )
    assert decimal.Decimal("1.10") <= decimal_value <= decimal.Decimal("1.20")
    assert decimal_value.as_tuple().exponent == -2

    bool_value = registry.get("bool").func(
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
    values = registry.get("list").func(
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
    set_values = registry.get("set").func(
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
    tuple_value = registry.get("tuple").func(
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
    mapping_value = registry.get("mapping").func(
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

    dt = registry.get("datetime").func(
        summary=FieldSummary(type="datetime", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(dt, datetime.datetime)

    d = registry.get("date").func(
        summary=FieldSummary(type="date", constraints=FieldConstraints()), faker=faker
    )
    assert isinstance(d, datetime.date)

    t = registry.get("time").func(
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

    identifier = registry.get("uuid").func(summary=summary["identifier"], faker=faker)
    assert isinstance(identifier, uuid.UUID)

    created = registry.get("datetime").func(summary=summary["created_at"], faker=faker)
    assert isinstance(created, datetime.datetime)

    birthday = registry.get("date").func(summary=summary["birthday"], faker=faker)
    assert isinstance(birthday, datetime.date)

    wake = registry.get("time").func(summary=summary["wake_up"], faker=faker)
    assert isinstance(wake, datetime.time)


def test_string_provider_regex_padding(monkeypatch) -> None:
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
