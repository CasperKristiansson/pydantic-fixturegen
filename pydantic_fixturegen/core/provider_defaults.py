"""Type-level provider default resolution."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic.fields import FieldInfo

from pydantic_fixturegen.core.config import (
    ConfigError,
    ProviderBundleConfig,
    ProviderDefaultsConfig,
    ProviderDefaultRule,
)
from pydantic_fixturegen.core.providers import ProviderRef, ProviderRegistry
from pydantic_fixturegen.core.schema import FieldSummary
from pydantic_fixturegen.core.seed_freeze import canonical_module_name


@dataclass(slots=True)
class ProviderDefaultMatch:
    """Resolved provider default rule applied to a field."""

    rule: ProviderDefaultRule
    bundle: ProviderBundleConfig
    provider: ProviderRef

    @property
    def provider_kwargs(self) -> Mapping[str, Any]:
        return self.bundle.provider_kwargs


class ProviderDefaultResolver:
    """Matches FieldSummary objects against configured provider default rules."""

    def __init__(
        self,
        config: ProviderDefaultsConfig | None,
        registry: ProviderRegistry,
    ) -> None:
        self._rules: tuple[ProviderDefaultRule, ...] = config.rules if config else ()
        self._bundle_refs: dict[str, tuple[ProviderBundleConfig, ProviderRef]] = {}
        if not config:
            return
        for bundle in config.bundles:
            provider = registry.get(bundle.provider, bundle.provider_format)
            if provider is None:
                fmt = f" format='{bundle.provider_format}'" if bundle.provider_format else ""
                raise ConfigError(
                    f"provider_defaults bundle '{bundle.name}' references unknown provider "
                    f"'{bundle.provider}'{fmt}."
                )
            self._bundle_refs[bundle.name] = (bundle, provider)

    def resolve(
        self,
        *,
        summary: FieldSummary,
        field_info: FieldInfo | None,
    ) -> ProviderDefaultMatch | None:
        if not self._rules:
            return None
        annotation_candidates = _annotation_candidates(summary, field_info)
        metadata_names = _metadata_names(summary, field_info)
        metadata_set = set(metadata_names)
        for rule in self._rules:
            if rule.summary_types and summary.type not in rule.summary_types:
                continue
            if rule.formats:
                if summary.format is None or summary.format not in rule.formats:
                    continue
            if rule.annotation_globs and not _match_annotation(annotation_candidates, rule.annotation_globs):
                continue
            if rule.metadata_all and not all(name in metadata_set for name in rule.metadata_all):
                continue
            if rule.metadata_any and not any(name in metadata_set for name in rule.metadata_any):
                continue
            bundle_ref = self._bundle_refs.get(rule.bundle)
            if not bundle_ref:
                continue
            bundle, provider = bundle_ref
            return ProviderDefaultMatch(rule=rule, bundle=bundle, provider=provider)
        return None


def _match_annotation(candidates: Sequence[str], patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
    return False


def _annotation_candidates(summary: FieldSummary, field_info: FieldInfo | None) -> tuple[str, ...]:
    candidates: list[str] = []
    annotation = summary.annotation
    descriptor = _describe_annotation(annotation)
    if descriptor:
        candidates.append(descriptor)
    if field_info is not None:
        descriptor = _describe_annotation(getattr(field_info, "annotation", None))
        if descriptor:
            candidates.append(descriptor)
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _metadata_names(summary: FieldSummary, field_info: FieldInfo | None) -> tuple[str, ...]:
    entries: list[Any] = list(summary.metadata)
    if field_info is not None:
        entries.extend(getattr(field_info, "metadata", ()) or ())
    names: list[str] = []
    for entry in entries:
        candidate = _describe_annotation(entry.__class__ if not isinstance(entry, type) else entry)
        if candidate:
            names.append(candidate)
    return tuple(dict.fromkeys(names))


def _describe_annotation(annotation: Any) -> str | None:
    if annotation is None:
        return None
    if isinstance(annotation, type):
        module = canonical_module_name(annotation)
        qualname = getattr(annotation, "__qualname__", getattr(annotation, "__name__", ""))
        if not qualname:
            return None
        return f"{module}.{qualname}" if module else qualname
    try:
        text = repr(annotation)
    except Exception:  # pragma: no cover - defensive fallback
        text = str(annotation)
    return text or None


__all__ = ["ProviderDefaultResolver", "ProviderDefaultMatch"]
