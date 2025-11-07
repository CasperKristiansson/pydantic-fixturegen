"""Identifier providers for emails, URLs, UUIDs, IPs, secrets, and payment cards."""

from __future__ import annotations

import ipaddress
import string
import uuid
from typing import Any

from pydantic import SecretBytes, SecretStr

from pydantic_fixturegen.core.config import IdentifierConfig
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary

_EMAIL_LOCAL_CHARS = string.ascii_lowercase + string.digits + "._"
_HOST_CHARS = string.ascii_lowercase + string.digits
_PATH_CHARS = string.ascii_lowercase + string.digits + "-_"
_TLDS = ("com", "net", "org", "io", "dev")
_CARD_PREFIXES = (
    ("4", 16),
    ("51", 16),
    ("34", 15),
    ("37", 15),
    ("6011", 16),
)
_MASK_EMAIL_DOMAIN = "example.com"
_MASK_URL_HOST = "example.invalid"
_MASK_PAYMENT_CARD = "4000000000000002"
_MASK_SECRET_VALUE = "REDACTED"


def generate_identifier(
    summary: FieldSummary,
    *,
    faker: Any | None = None,
    random_generator: Any | None = None,
    identifier_config: IdentifierConfig | None = None,
) -> Any:
    type_name = summary.type
    config = identifier_config or IdentifierConfig()
    rng = random_generator
    _ = faker  # keep signature compatibility; deterministic logic relies on rng

    if rng is None:
        raise RuntimeError("Identifier provider requires a seeded random generator.")

    if type_name == "email":
        return _generate_email(summary, rng, config)
    if type_name == "url":
        return _generate_url(summary, rng, config)
    if type_name == "uuid":
        return _generate_uuid(rng, config.uuid_version)
    if type_name == "payment-card":
        return _generate_payment_card(rng, config)
    if type_name == "secret-str":
        return _generate_secret_str(summary, rng, config)
    if type_name == "secret-bytes":
        return _generate_secret_bytes(summary, rng, config)
    if type_name == "ip-address":
        return _generate_ip_address(rng, config)
    if type_name == "ip-interface":
        return _generate_ip_interface(rng, config)
    if type_name == "ip-network":
        return _generate_ip_network(rng, config)

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


def _resolve_length(summary: FieldSummary, default_length: int) -> int:
    constraints = summary.constraints
    minimum = constraints.min_length or default_length
    maximum = constraints.max_length or default_length
    if minimum > maximum:
        minimum = maximum
    length = default_length
    if length < minimum:
        length = minimum
    if length > maximum:
        length = maximum
    return max(1, length)


def _generate_email(summary: FieldSummary, rng: Any, config: IdentifierConfig) -> str:
    constraints = summary.constraints
    min_total = constraints.min_length or 3
    max_total = constraints.max_length

    # Reserve at least two characters for "@" and domain
    if max_total is not None and max_total < 3:
        return "a@b"[:max_total]

    if config.mask_sensitive:
        domain = _MASK_EMAIL_DOMAIN
    else:
        domain_label_length = _choose_length(rng, 3, 10)
        domain_label = _random_string(rng, domain_label_length, _HOST_CHARS)
        tld = rng.choice(_TLDS)
        domain = f"{domain_label}.{tld}"

    if max_total is not None:
        max_domain_length = max(max_total - 2, 1)
        if len(domain) > max_domain_length:
            domain = domain[:max_domain_length]

    suffix = f"@{domain}"
    if max_total is not None and len(suffix) >= max_total:
        truncated = f"a{suffix}"
        return truncated[:max_total]

    min_local = max(1, min_total - len(suffix))
    max_local = None
    if max_total is not None:
        max_local = max(1, max_total - len(suffix))
    local_length = _choose_length(rng, min_local, max_local, default=8)
    if config.mask_sensitive:
        local_part = _masked_local_part(rng, local_length)
    else:
        local_part = _random_string(rng, local_length, _EMAIL_LOCAL_CHARS)
    email = f"{local_part}{suffix}"

    if len(email) < min_total:
        email += _random_string(rng, min_total - len(email), _EMAIL_LOCAL_CHARS)
    if max_total is not None and len(email) > max_total:
        email = email[:max_total]
        if "@" not in email:
            email = email[:-1] + "@"
    return email


def _generate_url(summary: FieldSummary, rng: Any, config: IdentifierConfig) -> str:
    constraints = summary.constraints
    min_length = constraints.min_length or 0
    max_length = constraints.max_length

    scheme = rng.choice(tuple(config.url_schemes))
    if config.mask_sensitive:
        host = "example"
        tld = "invalid"
    else:
        host_length = _choose_length(rng, 3, 12)
        host = _random_string(rng, host_length, _HOST_CHARS)
        tld = rng.choice(_TLDS)
    base = f"{scheme}://{host}.{tld}"

    url = base
    if config.url_include_path:
        if config.mask_sensitive:
            token = f"resource-{rng.randint(0, 9999):04d}"
            path = token
        else:
            path_segments = []
            segment_count = rng.randint(1, 3)
            for _ in range(segment_count):
                segment_length = _choose_length(rng, 2, 8)
                path_segments.append(_random_string(rng, segment_length, _PATH_CHARS))
            path = "/".join(path_segments)
        url = f"{base}/{path}"

    if len(url) < min_length:
        padding = _random_string(rng, min_length - len(url), _PATH_CHARS)
        separator = "" if url.endswith("/") else "/"
        url = f"{url}{separator}{padding}"

    if max_length is not None and len(url) > max_length:
        url = url[:max_length]
        if "://" not in url:
            url = base[:max_length]
    return url


def _generate_uuid(rng: Any, version: int) -> uuid.UUID:
    if version == 1:
        time_low = rng.getrandbits(32)
        time_mid = rng.getrandbits(16)
        time_hi = rng.getrandbits(12)
        time_hi_version = (time_hi & 0x0FFF) | 0x1000
        clock_seq = rng.getrandbits(14)
        clock_seq_hi_variant = ((clock_seq >> 8) & 0x3F) | 0x80
        clock_seq_low = clock_seq & 0xFF
        node = rng.getrandbits(48)
        return uuid.UUID(
            fields=(
                time_low,
                time_mid,
                time_hi_version,
                clock_seq_hi_variant,
                clock_seq_low,
                node,
            )
        )
    if version == 4:
        raw = bytearray(rng.getrandbits(8) for _ in range(16))
        raw[6] = (raw[6] & 0x0F) | 0x40
        raw[8] = (raw[8] & 0x3F) | 0x80
        return uuid.UUID(bytes=bytes(raw))
    raise ValueError(f"Unsupported UUID version: {version}")


def _generate_payment_card(rng: Any, config: IdentifierConfig) -> str:
    if config.mask_sensitive:
        return _MASK_PAYMENT_CARD
    prefix, length = rng.choice(_CARD_PREFIXES)
    digits = [int(char) for char in prefix]
    body_length = length - len(prefix) - 1
    for _ in range(body_length):
        digits.append(rng.randint(0, 9))
    check_digit = _luhn_check_digit(digits)
    digits.append(check_digit)
    return "".join(str(d) for d in digits)


def _generate_secret_str(summary: FieldSummary, rng: Any, config: IdentifierConfig) -> SecretStr:
    charset = string.ascii_letters + string.digits
    length = _resolve_length(summary, config.secret_str_length)
    if config.mask_sensitive:
        mask = (_MASK_SECRET_VALUE * ((length // len(_MASK_SECRET_VALUE)) + 1))[:length]
        value = mask or _MASK_SECRET_VALUE
    else:
        value = "".join(rng.choice(charset) for _ in range(length))
    return SecretStr(value)


def _generate_secret_bytes(
    summary: FieldSummary,
    rng: Any,
    config: IdentifierConfig,
) -> SecretBytes:
    length = _resolve_length(summary, config.secret_bytes_length)
    if config.mask_sensitive:
        data = bytes([0] * length)
    else:
        data = bytes(rng.getrandbits(8) for _ in range(length))
    return SecretBytes(data)


def _generate_ip_address(rng: Any, config: IdentifierConfig) -> str:
    if config.mask_sensitive:
        return f"192.0.2.{rng.randint(0, 255)}"
    return str(ipaddress.IPv4Address(rng.getrandbits(32)))


def _generate_ip_interface(rng: Any, config: IdentifierConfig) -> str:
    address = _generate_ip_address(rng, config)
    prefix = rng.randint(8, 30)
    return str(ipaddress.ip_interface(f"{address}/{prefix}"))


def _generate_ip_network(rng: Any, config: IdentifierConfig) -> str:
    address = _generate_ip_address(rng, config)
    prefix = rng.randint(8, 30)
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def _masked_local_part(rng: Any, target_length: int) -> str:
    token = f"user-{rng.randint(0, 999999):06d}"
    if len(token) < target_length:
        token += "0" * (target_length - len(token))
    return token[: max(1, target_length)]


def _random_string(rng: Any, length: int, alphabet: str) -> str:
    return "".join(rng.choice(alphabet) for _ in range(max(1, length)))


def _choose_length(rng: Any, minimum: int, maximum: int | None, default: int | None = None) -> int:
    minimum = max(1, minimum)
    if maximum is not None:
        maximum = max(minimum, maximum)
        if minimum == maximum:
            return minimum
        return int(rng.randint(minimum, maximum))
    if default is not None:
        return max(minimum, default)
    return minimum


def _luhn_check_digit(digits: list[int]) -> int:
    total = 0
    parity = (len(digits) + 1) % 2
    for index, digit in enumerate(digits):
        value = digit
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - (total % 10)) % 10
