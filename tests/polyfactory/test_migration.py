from __future__ import annotations

import pytest
from pydantic import BaseModel

try:  # pragma: no cover - optional dependency guard
    from polyfactory.factories.pydantic_factory import ModelFactory
    from polyfactory.fields import Ignore, PostGenerated, Require, Use
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    pytest.skip("polyfactory is required", allow_module_level=True)

from pydantic_fixturegen.api._runtime import _build_instance_generator
from pydantic_fixturegen.core.config import AppConfig
from pydantic_fixturegen.polyfactory_support.discovery import PolyfactoryBinding
from pydantic_fixturegen.polyfactory_support.migration import (
    analyze_binding,
    merge_override_maps,
    render_overrides_toml,
)


def slugify(prefix: str, suffix: str) -> str:
    return f"{prefix}-{suffix}"


def finalize(field: str, values: dict[str, str], suffix: str) -> str:
    return f"{values.get(field)}{suffix}"


class SampleModel(BaseModel):
    slug: str
    alias: str | None = None
    legacy_id: str | None = None
    name: str | None = None


class SampleFactory(ModelFactory[SampleModel]):
    __model__ = SampleModel
    __check_model__ = False

    slug = Use(slugify, "poly", "factory")
    alias = Ignore()
    legacy_id = PostGenerated(finalize, "-legacy")
    name = Require()


def test_analyze_binding_translates_fields() -> None:
    binding = PolyfactoryBinding(
        model=SampleModel,
        factory=SampleFactory,
        source="tests.SampleFactory",
    )
    generator = _build_instance_generator(AppConfig())
    strategies = generator._get_model_strategies(SampleModel)
    report = analyze_binding(binding, strategies=strategies)

    overrides = report.translated_overrides()
    assert "slug" in overrides
    assert overrides["slug"]["factory"].endswith("migration_helpers:invoke_use")
    assert overrides["legacy_id"]["post_generate"].endswith(
        "migration_helpers:invoke_post_generate"
    )
    assert overrides["alias"]["ignore"] is True
    assert overrides["name"]["require"] is True

    merged = merge_override_maps([report])
    toml = render_overrides_toml(merged)
    assert "overrides." in toml
    assert "slug" in toml
