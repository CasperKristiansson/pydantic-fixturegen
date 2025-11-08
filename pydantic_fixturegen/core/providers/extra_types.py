# coverage: ignore file
"""Providers for shapes defined in `pydantic-extra-types`."""

from __future__ import annotations

import datetime as _dt
import random
from collections.abc import Callable
from typing import Any

from pydantic_fixturegen.core.extra_types import available_type_ids
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary

_RNG = random.Random


def register_extra_type_providers(registry: ProviderRegistry) -> None:
    """Register providers for the subset of extra types available in the environment."""

    available = set(available_type_ids())
    for type_id, generator in _EXTRA_GENERATORS.items():
        if type_id not in available:
            continue
        registry.register(
            type_id,
            generator,
            name=f"extra.{type_id}",
            metadata={"library": "pydantic-extra-types", "type": type_id},
        )


def _ensure_rng(random_generator: random.Random | None) -> random.Random:
    return random_generator if random_generator is not None else _RNG()


def _bounded_float(
    summary: FieldSummary,
    default_min: float,
    default_max: float,
) -> tuple[float, float]:
    constraints = summary.constraints
    lower = constraints.ge if constraints.ge is not None else default_min
    upper = constraints.le if constraints.le is not None else default_max
    if lower > upper:
        lower, upper = upper, lower
    return float(lower), float(upper)


def _sample_float(
    summary: FieldSummary,
    default_min: float,
    default_max: float,
    rng: random.Random,
) -> float:
    lower, upper = _bounded_float(summary, default_min, default_max)
    if lower == upper:
        return lower
    return rng.uniform(lower, upper)


def _random_choice(rng: random.Random, values: tuple[str, ...]) -> str:
    return rng.choice(values)


def _random_domain(rng: random.Random) -> str:
    token = rng.choice(("api", "app", "svc", "edge"))
    suffix = rng.randint(1, 9999)
    tld = rng.choice(("com", "net", "io", "dev"))
    return f"{token}{suffix}.example.{tld}"


def _random_color(rng: random.Random) -> str:
    channels = [rng.randint(0, 255) for _ in range(3)]
    if rng.random() < 0.2:
        channels.append(rng.randint(0, 255))
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _random_mac(rng: random.Random) -> str:
    octets = [rng.randint(0, 255) for _ in range(6)]
    return ":".join(f"{octet:02x}" for octet in octets)


def _random_object_id(rng: random.Random) -> str:
    value = rng.getrandbits(96)
    return f"{value:024x}"


def _random_phone(rng: random.Random) -> str:
    area = rng.randint(200, 999)
    exchange = rng.randint(200, 999)
    line = rng.randint(0, 9999)
    return f"+1{area:03d}{exchange:03d}{line:04d}"


def _random_s3_path(rng: random.Random) -> str:
    bucket = f"data-{rng.randint(1000, 9999)}"
    year = rng.randint(2018, 2035)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    shard = rng.randint(0, 9999)
    key = f"{year}/{month:02d}/{day:02d}/batch-{shard:04d}.json"
    return f"s3://{bucket}/{key}"


def _random_cron(rng: random.Random) -> str:
    step = rng.choice((1, 2, 5, 10, 15, 30))
    minute = f"*/{step}"
    hour = rng.choice(("*", "*/6", "*/12"))
    dom = "*"
    month = "*"
    dow = rng.choice(("*", "1-5"))
    return f"{minute} {hour} {dom} {month} {dow}"


def _random_semver(rng: random.Random) -> str:
    return f"{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 30)}"


def _random_ulid(rng: random.Random) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return "".join(rng.choice(alphabet) for _ in range(26))


def _random_timezone(rng: random.Random) -> str:
    return rng.choice(("UTC", "America/New_York", "Europe/Stockholm", "Asia/Tokyo"))


def _random_isbn(rng: random.Random) -> str:
    prefix = "978"
    body = f"{rng.randint(0, 999999999):09d}"
    raw = prefix + body
    total = sum(int(digit) * factor for digit, factor in zip(raw, (1, 3) * 6, strict=False))
    check = (10 - (total % 10)) % 10
    return raw + str(check)


def _generate_color(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_color(rng)


def _generate_latitude(summary: FieldSummary, **kwargs: Any) -> float:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return round(_sample_float(summary, -90.0, 90.0, rng), 6)


def _generate_longitude(summary: FieldSummary, **kwargs: Any) -> float:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return round(_sample_float(summary, -180.0, 180.0, rng), 6)


def _generate_coordinate(summary: FieldSummary, **kwargs: Any) -> tuple[float, float]:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return (
        round(rng.uniform(-90.0, 90.0), 6),
        round(rng.uniform(-180.0, 180.0), 6),
    )


def _generate_choice(summary: FieldSummary, *, choices: tuple[str, ...], **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_choice(rng, choices)


def _generate_domain(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_domain(rng)


def _generate_cron(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_cron(rng)


def _generate_epoch_number(summary: FieldSummary, **kwargs: Any) -> float:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return round(rng.uniform(0, 86_400 * 365), 3)


def _generate_epoch_integer(summary: FieldSummary, **kwargs: Any) -> int:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return int(rng.uniform(0, 86_400 * 365))


def _generate_mac(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_mac(rng)


def _generate_object_id(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_object_id(rng)


def _generate_phone(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_phone(rng)


def _generate_routing_number(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    digits = [rng.randint(0, 9) for _ in range(8)]
    checksum = (10 - (sum(d * f for d, f in zip(digits, (3, 7, 1) * 3, strict=False)) % 10)) % 10
    digits.append(checksum)
    return "".join(str(d) for d in digits)


def _generate_s3(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_s3_path(rng)


def _generate_semver(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_semver(rng)


def _generate_timezone(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_timezone(rng)


def _generate_ulid(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_ulid(rng)


def _generate_duration(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    hours = rng.randint(1, 12)
    minutes = rng.randint(0, 59)
    return f"PT{hours}H{minutes}M"


def _generate_time(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"


def _generate_date(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    day = rng.randint(1, 28)
    month = rng.randint(1, 12)
    year = rng.randint(2020, 2035)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _generate_datetime(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    base = _dt.datetime(2020, 1, 1, tzinfo=_dt.timezone.utc)
    delta = _dt.timedelta(minutes=rng.randint(0, 60 * 24 * 365))
    return (base + delta).isoformat()


_CHOICE_VALUES: dict[str, tuple[str, ...]] = {
    "country-alpha2": ("US", "GB", "SE", "DE", "BR"),
    "country-alpha3": ("USA", "GBR", "SWE", "DEU", "BRA"),
    "country-numeric": ("840", "826", "752", "276"),
    "currency-iso4217": ("USD", "EUR", "GBP", "JPY", "SEK"),
    "currency": ("USD", "EUR", "GBP", "CAD"),
    "language-alpha2": ("en", "sv", "de", "es"),
    "language-name": ("English", "Swedish", "German", "Spanish"),
    "language-iso639-3": ("eng", "swe", "deu", "spa"),
    "language-iso639-5": ("gem", "roa", "sla"),
    "script-code": ("Latn", "Cyrl", "Grek"),
}


def _choice_provider(type_id: str) -> Callable[[FieldSummary], str]:
    def _provider(summary: FieldSummary, **kwargs: Any) -> str:
        return _generate_choice(summary, choices=_CHOICE_VALUES[type_id], **kwargs)

    return _provider


_EXTRA_GENERATORS: dict[str, Any] = {
    "color": _generate_color,
    "latitude": _generate_latitude,
    "longitude": _generate_longitude,
    "coordinate": _generate_coordinate,
    "country-alpha2": _choice_provider("country-alpha2"),
    "country-alpha3": _choice_provider("country-alpha3"),
    "country-numeric": _choice_provider("country-numeric"),
    "cron": _generate_cron,
    "currency-iso4217": _choice_provider("currency-iso4217"),
    "currency": _choice_provider("currency"),
    "domain": _generate_domain,
    "epoch-number": _generate_epoch_number,
    "epoch-integer": _generate_epoch_integer,
    "isbn": lambda summary, **kw: _generate_isbn(summary, **kw),
    "language-alpha2": _choice_provider("language-alpha2"),
    "language-name": _choice_provider("language-name"),
    "language-iso639-3": _choice_provider("language-iso639-3"),
    "language-iso639-5": _choice_provider("language-iso639-5"),
    "mac-address": _generate_mac,
    "mongo-object-id": _generate_object_id,
    "pendulum-datetime": _generate_datetime,
    "pendulum-time": _generate_time,
    "pendulum-date": _generate_date,
    "pendulum-duration": _generate_duration,
    "phone-number": _generate_phone,
    "routing-number": _generate_routing_number,
    "s3-path": _generate_s3,
    "script-code": _choice_provider("script-code"),
    "semantic-version": _generate_semver,
    "timezone-name": _generate_timezone,
    "ulid": _generate_ulid,
}


def _generate_isbn(summary: FieldSummary, **kwargs: Any) -> str:
    rng = _ensure_rng(kwargs.get("random_generator"))
    return _random_isbn(rng)


__all__ = ["register_extra_type_providers"]
