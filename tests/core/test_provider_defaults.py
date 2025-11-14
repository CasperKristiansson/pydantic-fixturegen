from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core import provider_defaults as provider_defaults_mod
from pydantic_fixturegen.core.config import (
    ConfigError,
    ProviderBundleConfig,
    ProviderDefaultRule,
    ProviderDefaultsConfig,
)
from pydantic_fixturegen.core.provider_defaults import ProviderDefaultResolver
from pydantic_fixturegen.core.providers.registry import ProviderRegistry
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _register_string_provider() -> ProviderRegistry:
    registry = ProviderRegistry()

    def provider(summary: FieldSummary, **kwargs):
        return summary.type

    registry.register("string", provider, name="string.default")
    return registry


def test_provider_default_resolver_matches_summary_type() -> None:
    registry = _register_string_provider()
    bundle = ProviderBundleConfig(name="bundle", provider="string")
    rule = ProviderDefaultRule(name="strings", bundle="bundle", summary_types=("string",))
    config = ProviderDefaultsConfig(bundles=(bundle,), rules=(rule,))
    resolver = ProviderDefaultResolver(config, registry)
    summary = FieldSummary(type="string", constraints=FieldConstraints(), annotation=str)

    match = resolver.resolve(summary=summary, field_info=None)

    assert match is not None
    assert match.provider.name == "string.default"
    assert match.provider_kwargs == {}


class _MetaOne:
    pass


class _MetaTwo:
    pass


def test_provider_default_resolver_respects_metadata_and_annotations() -> None:
    registry = _register_string_provider()
    bundle = ProviderBundleConfig(name="bundle", provider="string")
    rule = ProviderDefaultRule(
        name="meta-rule",
        bundle="bundle",
        annotation_globs=("*.FieldSummary", "*int"),
        metadata_all=(f"{__name__}._MetaOne",),
        metadata_any=(f"{__name__}._MetaTwo",),
    )
    config = ProviderDefaultsConfig(bundles=(bundle,), rules=(rule,))
    resolver = ProviderDefaultResolver(config, registry)
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(),
        annotation=FieldSummary,
        metadata=(_MetaOne(),),
    )
    field_info = SimpleNamespace(annotation=int, metadata=(_MetaTwo(),))

    match = resolver.resolve(summary=summary, field_info=field_info)  # type: ignore[arg-type]

    assert match is not None
    assert match.rule.name == "meta-rule"


def test_provider_default_resolver_requires_known_bundle() -> None:
    registry = ProviderRegistry()
    config = ProviderDefaultsConfig(
        bundles=(),
        rules=(ProviderDefaultRule(name="missing", bundle="not-found"),),
    )
    resolver = ProviderDefaultResolver(config, registry)
    summary = FieldSummary(type="string", constraints=FieldConstraints())

    assert resolver.resolve(summary=summary, field_info=None) is None

    with pytest.raises(ConfigError):
        ProviderDefaultResolver(
            ProviderDefaultsConfig(
                bundles=(ProviderBundleConfig(name="bundle", provider="missing"),),
                rules=(),
            ),
            registry,
        )


def test_annotation_and_metadata_helpers() -> None:
    summary = FieldSummary(
        type="string",
        constraints=FieldConstraints(),
        annotation=int,
        metadata=(_MetaOne(), _MetaTwo()),
    )
    field_info = SimpleNamespace(annotation=str, metadata=(int,))

    candidates = provider_defaults_mod._annotation_candidates(summary, field_info)  # type: ignore[arg-type]
    assert any("int" in candidate for candidate in candidates)

    metadata = provider_defaults_mod._metadata_names(summary, field_info)  # type: ignore[arg-type]
    assert f"{__name__}._MetaOne" in metadata

    assert provider_defaults_mod._match_annotation(candidates, ("*.int",))
    assert not provider_defaults_mod._match_annotation(candidates, ("*.missing",))

    class Alias:
        def __repr__(self) -> str:
            return "alias"

    assert provider_defaults_mod._describe_annotation(Alias()) == "alias"
