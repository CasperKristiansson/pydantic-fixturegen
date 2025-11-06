from __future__ import annotations

import ipaddress
import random

import pytest
from pydantic_fixturegen.core.config import IdentifierConfig
from pydantic_fixturegen.core.providers import identifiers as identifiers_mod
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(type_name: str, **constraints: object) -> FieldSummary:
    return FieldSummary(type=type_name, constraints=FieldConstraints(**constraints))


def test_generate_identifier_requires_seeded_rng() -> None:
    with pytest.raises(RuntimeError):
        identifiers_mod.generate_identifier(_summary("email"), random_generator=None)  # type: ignore[arg-type]


def test_generate_identifier_email_respects_bounds() -> None:
    rng = random.Random(0)
    summary = _summary("email", min_length=10, max_length=20)

    value = identifiers_mod.generate_identifier(summary, random_generator=rng)

    assert "@" in value
    assert 10 <= len(value) <= 20


def test_generate_identifier_url_includes_path() -> None:
    rng = random.Random(1)
    config = IdentifierConfig(url_schemes=("http", "https"), url_include_path=True)
    summary = _summary("url", min_length=15)

    url = identifiers_mod.generate_identifier(
        summary,
        random_generator=rng,
        identifier_config=config,
    )

    assert url.startswith(("http://", "https://"))
    assert "/" in url.split("://", 1)[1]
    assert len(url) >= 15


def test_generate_identifier_uuid_versions() -> None:
    rng = random.Random(2)
    uuid_v1 = identifiers_mod.generate_identifier(
        _summary("uuid"),
        random_generator=rng,
        identifier_config=IdentifierConfig(uuid_version=1),
    )
    assert uuid_v1.version == 1

    uuid_v4 = identifiers_mod.generate_identifier(
        _summary("uuid"),
        random_generator=random.Random(3),
        identifier_config=IdentifierConfig(uuid_version=4),
    )
    assert uuid_v4.version == 4


def test_generate_identifier_secret_values_use_config_lengths() -> None:
    rng = random.Random(4)
    config = IdentifierConfig(secret_str_length=12, secret_bytes_length=6)

    secret_str = identifiers_mod.generate_identifier(
        _summary("secret-str", min_length=5, max_length=20),
        random_generator=rng,
        identifier_config=config,
    )
    assert len(secret_str) == 12

    secret_bytes = identifiers_mod.generate_identifier(
        _summary("secret-bytes", min_length=4, max_length=10),
        random_generator=random.Random(5),
        identifier_config=config,
    )
    assert len(secret_bytes) == 6


def test_generate_identifier_payment_card_and_ip_types() -> None:
    rng = random.Random(6)
    summary_card = _summary("payment-card")
    card = identifiers_mod.generate_identifier(summary_card, random_generator=rng)
    assert len(card) in {15, 16}
    assert card.isdigit()

    addr = identifiers_mod.generate_identifier(
        _summary("ip-address"),
        random_generator=random.Random(7),
    )
    ip = ipaddress.ip_address(addr)
    assert isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address))

    interface = identifiers_mod.generate_identifier(
        _summary("ip-interface"),
        random_generator=random.Random(8),
    )
    assert "/" in interface
    ipaddress.ip_interface(interface)

    network = identifiers_mod.generate_identifier(
        _summary("ip-network"),
        random_generator=random.Random(9),
    )
    ipaddress.ip_network(network, strict=False)


def test_generate_identifier_unknown_type() -> None:
    with pytest.raises(ValueError):
        identifiers_mod.generate_identifier(_summary("custom"), random_generator=random.Random())


def test_resolve_length_clamps_and_defaults() -> None:
    summary = _summary("secret-str", min_length=10, max_length=4)
    assert identifiers_mod._resolve_length(summary, default_length=8) == 4

    summary2 = _summary("secret-str", min_length=None, max_length=7)
    assert identifiers_mod._resolve_length(summary2, default_length=3) == 3


def test_generate_email_handles_short_max() -> None:
    summary = _summary("email", min_length=None, max_length=2)
    assert identifiers_mod._generate_email(summary, random.Random(0)) == "a@"


def test_generate_url_without_path_padding() -> None:
    config = IdentifierConfig(url_schemes=("http",), url_include_path=False)
    summary = _summary("url", min_length=25, max_length=30)
    value = identifiers_mod._generate_url(summary, random.Random(0), config)
    assert value.startswith("http://")
    assert len(value) >= 25


def test_generate_uuid_invalid_version() -> None:
    with pytest.raises(ValueError):
        identifiers_mod._generate_uuid(random.Random(0), 2)


def test_choose_length_defaults_and_bounds() -> None:
    rng = random.Random(0)
    assert identifiers_mod._choose_length(rng, 5, 5) == 5
    assert identifiers_mod._choose_length(rng, 2, None, default=6) == 6
