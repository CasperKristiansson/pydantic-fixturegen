from __future__ import annotations

import datetime
import random
import uuid
from typing import Any

import pytest
from faker import Faker
from pydantic import BaseModel, SecretBytes, SecretStr, constr

from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary
from pydantic_fixturegen.core.providers import ProviderRef, ProviderRegistry
from pydantic_fixturegen.core.providers import strings as strings_module
from pydantic_fixturegen.core.providers.strings import register_string_providers
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

    registry.load_entrypoint_plugins()
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

    email_summary = FieldSummary(type="string", constraints=FieldConstraints(), format="email")
    email_value = provider.func(summary=email_summary, faker=faker)
    assert "@" in email_value

    card_summary = FieldSummary(type="string", constraints=FieldConstraints(), format="payment-card")
    card_value = provider.func(summary=card_summary, faker=faker)
    assert isinstance(card_value, str) and len(card_value) > 0

    url_summary = FieldSummary(type="string", constraints=FieldConstraints(), format="url")
    url_value = provider.func(summary=url_summary, faker=faker)
    assert url_value.startswith("http")

    plain_summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=2, max_length=3),
        format=None,
    )
    plain_value = provider.func(summary=plain_summary, faker=faker, random_generator=random.Random(1))
    assert 2 <= len(plain_value) <= 3


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
    register_string_providers(registry)
    provider = registry.get("string")
    assert provider is not None

    class TemporalModel(BaseModel):
        identifier: uuid.UUID
        created_at: datetime.datetime
        birthday: datetime.date
        wake_up: datetime.time

    summary = schema_module.summarize_model_fields(TemporalModel)
    faker = Faker(seed=5)

    identifier = provider.func(summary=summary["identifier"], faker=faker)
    assert len(identifier) == 36 and identifier.count("-") == 4

    created = provider.func(summary=summary["created_at"], faker=faker)
    assert "T" in created

    birthday = provider.func(summary=summary["birthday"], faker=faker)
    assert "-" in birthday

    wake = provider.func(summary=summary["wake_up"], faker=faker)
    assert ":" in wake


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
