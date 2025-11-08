from __future__ import annotations

import random

import pytest
from pydantic_fixturegen.core import schema as schema_module
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.providers import extra_types as extra_mod
from pydantic_fixturegen.core.schema import FieldConstraints

try:
    from pydantic_extra_types.color import Color
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    Color = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.domain import DomainStr
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    DomainStr = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.epoch import Number as EpochNumber
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    EpochNumber = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.isbn import ISBN
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    ISBN = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.mac_address import MacAddress
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    MacAddress = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.semantic_version import SemanticVersion
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    SemanticVersion = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.s3 import S3Path
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    S3Path = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.timezone_name import TimeZoneName
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    TimeZoneName = None  # type: ignore[assignment]

try:
    from pydantic_extra_types.ulid import ULID
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional dependency not installed
    ULID = None  # type: ignore[assignment]


@pytest.mark.skipif(Color is None, reason="pydantic-extra-types[color] not available")
def test_color_provider_generates_hex() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("color")
    assert provider is not None

    summary = schema_module._summarize_annotation(Color, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert value.startswith("#")
    assert len(value) in (7, 9)


@pytest.mark.skipif(S3Path is None, reason="pydantic-extra-types[s3] not available")
def test_s3_path_provider_generates_prefixed_uri() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("s3-path")
    assert provider is not None

    summary = schema_module._summarize_annotation(S3Path, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert value.startswith("s3://")
    assert "/" in value[len("s3://") :]


@pytest.mark.skipif(DomainStr is None, reason="pydantic-extra-types[domain] not available")
def test_domain_provider_generates_hostname() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("domain")
    assert provider is not None

    summary = schema_module._summarize_annotation(DomainStr, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert value.endswith((".com", ".net", ".io", ".dev"))


@pytest.mark.skipif(EpochNumber is None, reason="pydantic-extra-types[epoch] not available")
def test_epoch_number_provider_returns_seconds() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("epoch-number")
    assert provider is not None

    summary = schema_module._summarize_annotation(EpochNumber, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, float)
    assert value >= 0


@pytest.mark.skipif(ISBN is None, reason="pydantic-extra-types[isbn] not available")
def test_isbn_provider_returns_string() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("isbn")
    assert provider is not None

    summary = schema_module._summarize_annotation(ISBN, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert len(value) == 13


@pytest.mark.skipif(MacAddress is None, reason="pydantic-extra-types[mac_address] not available")
def test_mac_address_provider_returns_hex_pairs() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("mac-address")
    assert provider is not None

    summary = schema_module._summarize_annotation(MacAddress, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert value.count(":") == 5


@pytest.mark.skipif(
    SemanticVersion is None, reason="pydantic-extra-types[semantic_version] not available"
)
def test_semantic_version_provider_returns_version_string() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("semantic-version")
    assert provider is not None

    summary = schema_module._summarize_annotation(SemanticVersion, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert value.count(".") == 2


@pytest.mark.skipif(
    TimeZoneName is None, reason="pydantic-extra-types[timezone_name] not available"
)
def test_timezone_name_provider_returns_region() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("timezone-name")
    assert provider is not None

    summary = schema_module._summarize_annotation(TimeZoneName, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert "/" in value or value == "UTC"


@pytest.mark.skipif(ULID is None, reason="pydantic-extra-types[ulid] not available")
def test_ulid_provider_returns_base32_string() -> None:
    registry = create_default_registry(load_plugins=False)
    provider = registry.get("ulid")
    assert provider is not None

    summary = schema_module._summarize_annotation(ULID, FieldConstraints())
    value = provider.func(summary)
    assert isinstance(value, str)
    assert len(value) == 26


def test_helper_functions_cover_random_paths() -> None:
    rng = random.Random(9)
    assert isinstance(extra_mod._ensure_rng(None), random.Random)
    assert extra_mod._random_phone(rng).startswith("+1")
    assert extra_mod._random_semver(random.Random(10)).count(".") == 2
    assert len(extra_mod._random_ulid(random.Random(11))) == 26
