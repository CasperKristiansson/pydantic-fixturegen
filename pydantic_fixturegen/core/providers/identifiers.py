"""Identifier providers for emails, URLs, UUIDs, IPs, secrets, and payment cards."""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

from faker import Faker
from pydantic import SecretBytes, SecretStr

from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary


def generate_identifier(
    summary: FieldSummary,
    *,
    faker: Faker | None = None,
) -> Any:
    faker = faker or Faker()
    type_name = summary.type

    if type_name == "email":
        return faker.unique.email()
    if type_name == "url":
        return faker.unique.url()
    if type_name == "uuid":
        return uuid.uuid4()
    if type_name == "payment-card":
        return faker.credit_card_number()
    if type_name == "secret-str":
        return SecretStr(faker.password())
    if type_name == "secret-bytes":
        return SecretBytes(faker.binary(length=16))
    if type_name == "ip-address":
        return faker.ipv4()
    if type_name == "ip-interface":
        address = faker.ipv4()
        return str(ipaddress.ip_interface(f"{address}/24"))
    if type_name == "ip-network":
        address = faker.ipv4()
        return str(ipaddress.ip_network(f"{address}/24", strict=False))

    raise ValueError(f"Unsupported identifier type: {type_name}")


def register_identifier_providers(registry: ProviderRegistry) -> None:
    for identifier_type in (
        "email",
        "url",
        "uuid",
        "payment-card",
        "secret-str",
        "secret-bytes",
        "ip-address",
        "ip-interface",
        "ip-network",
    ):
        registry.register(
            identifier_type,
            generate_identifier,
            name=f"identifier.{identifier_type}",
            metadata={"type": identifier_type},
        )


__all__ = ["generate_identifier", "register_identifier_providers"]
