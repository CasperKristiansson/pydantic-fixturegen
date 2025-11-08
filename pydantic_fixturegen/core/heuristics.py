"""Heuristic provider mapping for strategy selection."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic.fields import FieldInfo

from pydantic_fixturegen.core.schema import FieldSummary
from pydantic_fixturegen.plugins.loader import (
    get_plugin_manager,
    load_entrypoint_plugins,
    register_plugin,
)


@dataclass(slots=True)
class HeuristicResult:
    """Intermediate evaluation result used while matching a rule."""

    signals: list[str] = field(default_factory=list)
    provider_kwargs: Mapping[str, Any] | None = None
    confidence: float | None = None


@dataclass(slots=True)
class HeuristicMatch:
    """Final decision returned when a rule selects a provider."""

    rule: str
    description: str
    provider_type: str
    provider_format: str | None
    confidence: float
    signals: tuple[str, ...]
    provider_kwargs: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "description": self.description,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "provider_type": self.provider_type,
            "provider_format": self.provider_format,
        }


@dataclass(slots=True)
class HeuristicContext:
    """Field context inspected by heuristic rules."""

    model: type[Any] | None
    field_name: str
    summary: FieldSummary
    field_info: FieldInfo | None
    alias: str | None
    path: str
    tokens: tuple[str, ...]
    metadata_tokens: tuple[str, ...]
    constraint_pattern: str | None


@dataclass(slots=True)
class HeuristicCondition:
    """Declarative rule matcher used by heuristics."""

    keywords_any: tuple[str, ...] = ()
    keywords_all: tuple[str, ...] = ()
    metadata_any: tuple[str, ...] = ()
    metadata_all: tuple[str, ...] = ()
    name_globs: tuple[str, ...] = ()
    summary_types: tuple[str, ...] = ()
    constraint_patterns: tuple[str, ...] = ()
    length_equals: int | None = None
    predicate: Callable[[HeuristicContext], HeuristicResult | None] | None = None
    _keywords_any: tuple[str, ...] = field(init=False, repr=False)
    _keywords_all: tuple[str, ...] = field(init=False, repr=False)
    _metadata_any: tuple[str, ...] = field(init=False, repr=False)
    _metadata_all: tuple[str, ...] = field(init=False, repr=False)
    _name_globs: tuple[str, ...] = field(init=False, repr=False)
    _constraint_regexes: tuple[re.Pattern[str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._keywords_any = tuple(token.lower() for token in self.keywords_any)
        self._keywords_all = tuple(token.lower() for token in self.keywords_all)
        self._metadata_any = tuple(token.lower() for token in self.metadata_any)
        self._metadata_all = tuple(token.lower() for token in self.metadata_all)
        self._name_globs = tuple(pattern.lower() for pattern in self.name_globs)
        self._constraint_regexes = tuple(
            re.compile(pattern, re.IGNORECASE) for pattern in self.constraint_patterns
        )

    def evaluate(self, context: HeuristicContext) -> HeuristicResult | None:
        summary = context.summary
        if self.summary_types and summary.type not in self.summary_types:
            return None

        reasons: list[str] = []
        token_set = set(context.tokens)
        metadata_set = set(context.metadata_tokens)

        if self._keywords_all:
            if not all(keyword in token_set for keyword in self._keywords_all):
                return None
            for keyword in self._keywords_all:
                reasons.append(f"keyword:{keyword}")

        if self._keywords_any:
            match = next((kw for kw in self._keywords_any if kw in token_set), None)
            if match is None:
                return None
            reasons.append(f"keyword:{match}")

        if self._metadata_all:
            if not all(tag in metadata_set for tag in self._metadata_all):
                return None
            for tag in self._metadata_all:
                reasons.append(f"metadata:{tag}")

        if self._metadata_any:
            match = next((tag for tag in self._metadata_any if tag in metadata_set), None)
            if match is None:
                return None
            reasons.append(f"metadata:{match}")

        if self._name_globs:
            haystack = [context.field_name.lower()]
            if context.alias:
                haystack.append(context.alias.lower())
            if not _match_globs(haystack, self._name_globs):
                return None
            reasons.append("field-name-pattern")

        if self._constraint_regexes:
            pattern = context.constraint_pattern or ""
            if not any(regex.search(pattern) for regex in self._constraint_regexes):
                return None
            reasons.append("constraint-pattern")

        if self.length_equals is not None:
            if not _length_matches(summary, self.length_equals):
                return None
            reasons.append(f"length:{self.length_equals}")

        if self.predicate is not None:
            custom = self.predicate(context)
            if custom is None:
                return None
            reasons.extend(custom.signals)
            return HeuristicResult(
                signals=reasons,
                provider_kwargs=custom.provider_kwargs,
                confidence=custom.confidence,
            )

        return HeuristicResult(signals=reasons)


@dataclass(slots=True)
class HeuristicRule:
    """Concrete rule that maps a condition onto a provider override."""

    name: str
    description: str
    provider_type: str
    provider_format: str | None = None
    priority: int = 0
    confidence: float = 0.6
    condition: HeuristicCondition | None = None
    matcher: Callable[[HeuristicContext], HeuristicResult | None] | None = None
    provider_kwargs: Mapping[str, Any] | None = None

    def evaluate(self, context: HeuristicContext) -> HeuristicMatch | None:
        result: HeuristicResult | None
        if self.matcher is not None:
            result = self.matcher(context)
        elif self.condition is not None:
            result = self.condition.evaluate(context)
        else:
            result = None

        if result is None:
            return None

        signals = tuple(result.signals)
        kwargs: Mapping[str, Any]
        if self.provider_kwargs and result.provider_kwargs:
            merged = dict(self.provider_kwargs)
            merged.update(result.provider_kwargs)
            kwargs = merged
        elif result.provider_kwargs:
            kwargs = result.provider_kwargs
        else:
            kwargs = self.provider_kwargs or {}

        confidence = result.confidence if result.confidence is not None else self.confidence

        return HeuristicMatch(
            rule=self.name,
            description=self.description,
            provider_type=self.provider_type,
            provider_format=self.provider_format,
            confidence=confidence,
            signals=signals,
            provider_kwargs=kwargs,
        )


class HeuristicRegistry:
    """Collection of heuristic rules evaluated in priority order."""

    def __init__(self) -> None:
        self._rules: list[HeuristicRule] = []
        self._plugin_manager = get_plugin_manager()

    def register(self, rule: HeuristicRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda item: (-item.priority, item.name))

    def register_plugin(self, plugin: Any) -> None:
        register_plugin(plugin)
        self._plugin_manager.hook.pfg_register_heuristics(registry=self)

    def clear(self) -> None:
        self._rules.clear()

    def evaluate(
        self,
        *,
        model: type[Any] | None,
        field_name: str,
        summary: FieldSummary,
        field_info: FieldInfo | None,
    ) -> HeuristicMatch | None:
        context = _build_context(model, field_name, summary, field_info)
        for rule in self._rules:
            match = rule.evaluate(context)
            if match is not None:
                return match
        return None

    def load_entrypoint_plugins(
        self,
        group: str = "pydantic_fixturegen",
        *,
        force: bool = False,
    ) -> None:
        plugins = load_entrypoint_plugins(group, force=force)
        if not plugins:
            return
        self._plugin_manager.hook.pfg_register_heuristics(registry=self)


def create_default_heuristic_registry(load_plugins: bool = True) -> HeuristicRegistry:
    registry = HeuristicRegistry()
    _register_builtin_rules(registry)
    if load_plugins:
        registry.load_entrypoint_plugins()
    return registry


# ---------------------------------------------------------------------------
# helpers


def _build_context(
    model: type[Any] | None,
    field_name: str,
    summary: FieldSummary,
    field_info: FieldInfo | None,
) -> HeuristicContext:
    alias = getattr(field_info, "alias", None)
    path = _describe_path(model, field_name)
    metadata_entries = list(summary.metadata)
    if field_info is not None:
        metadata_entries.extend(field_info.metadata)
    metadata_tokens = _collect_metadata_tokens(metadata_entries)

    text_sources: list[str] = [field_name]
    if alias:
        text_sources.append(alias)
    if field_info is not None:
        title = getattr(field_info, "title", None)
        description = getattr(field_info, "description", None)
        if title:
            text_sources.append(title)
        if description:
            text_sources.append(description)
        json_schema = getattr(field_info, "json_schema_extra", None) or {}
        fmt = json_schema.get("format")
        if isinstance(fmt, str):
            text_sources.append(fmt)
    if summary.format:
        text_sources.append(summary.format)
    text_sources.extend(metadata_tokens)

    tokens = _tokenize_sources(text_sources)

    return HeuristicContext(
        model=model,
        field_name=field_name,
        summary=summary,
        field_info=field_info,
        alias=alias,
        path=path,
        tokens=tokens,
        metadata_tokens=tuple(metadata_tokens),
        constraint_pattern=summary.constraints.pattern,
    )


def _describe_path(model: type[Any] | None, field_name: str) -> str:
    if model is None:
        return field_name
    module = getattr(model, "__module__", "")
    qualname = getattr(model, "__qualname__", getattr(model, "__name__", ""))
    prefix = f"{module}.{qualname}" if module else qualname
    return f"{prefix}.{field_name}" if prefix else field_name


_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z]+")
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokenize_sources(sources: Iterable[str]) -> tuple[str, ...]:
    tokens: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for token in _tokenize(source):
            if token not in seen:
                tokens.append(token)
                seen.add(token)
    return tuple(tokens)


def _tokenize(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = _CAMEL_SPLIT.sub(" ", value).lower()
    parts = _TOKEN_SPLIT.split(normalized)
    return [part for part in parts if part]


def _collect_metadata_tokens(metadata: Sequence[Any]) -> list[str]:
    tokens: list[str] = []
    for entry in metadata:
        if isinstance(entry, str):
            tokens.extend(_tokenize(entry))
        elif hasattr(entry, "alias") and isinstance(entry.alias, str):
            tokens.extend(_tokenize(entry.alias))
    return tokens


def _match_globs(values: Sequence[str], patterns: Sequence[str]) -> bool:
    lowered = [value.lower() for value in values if value]
    for pattern in patterns:
        if any(fnmatch.fnmatchcase(value, pattern) for value in lowered):
            return True
    return False


def _length_matches(summary: FieldSummary, expected: int) -> bool:
    constraints = summary.constraints
    candidates = [constraints.min_length, constraints.max_length]
    defined = [value for value in candidates if value is not None]
    if not defined:
        return False
    return all(value == expected for value in defined)


# ---------------------------------------------------------------------------
# built-in rules


def _register_builtin_rules(registry: HeuristicRegistry) -> None:
    registry.register(
        HeuristicRule(
            name="string-email",
            description="Field label implies an email address",
            provider_type="email",
            priority=90,
            confidence=0.95,
            condition=HeuristicCondition(
                keywords_any=("email",),
                summary_types=("string", "secret-str"),
            ),
        )
    )
    registry.register(
        HeuristicRule(
            name="string-url",
            description="Field label implies a URL",
            provider_type="url",
            priority=85,
            confidence=0.85,
            condition=HeuristicCondition(
                keywords_any=("url", "website", "homepage", "link", "endpoint", "callback"),
                summary_types=("string",),
            ),
        )
    )
    registry.register(
        HeuristicRule(
            name="string-uuid",
            description="Field label references UUID/GUID",
            provider_type="uuid",
            priority=80,
            confidence=0.8,
            condition=HeuristicCondition(
                keywords_any=("uuid", "guid"),
                summary_types=("string",),
            ),
        )
    )
    registry.register(
        HeuristicRule(
            name="string-slug",
            description="Field labeled as slug",
            provider_type="slug",
            priority=82,
            confidence=0.88,
            condition=HeuristicCondition(
                keywords_any=("slug",),
                summary_types=("string",),
            ),
        )
    )
    registry.register(
        HeuristicRule(
            name="path-directory",
            description="Field name implies directory path",
            provider_type="path",
            priority=78,
            confidence=0.75,
            condition=HeuristicCondition(
                keywords_any=("dir", "directory", "folder"),
                summary_types=("string",),
            ),
            provider_kwargs={"preferred_kind": "directory"},
        )
    )
    registry.register(
        HeuristicRule(
            name="path-file",
            description="Field name implies filesystem path",
            provider_type="path",
            priority=70,
            confidence=0.72,
            condition=HeuristicCondition(
                keywords_any=("path", "filepath", "filename", "file", "pathname", "basename"),
                summary_types=("string",),
            ),
            provider_kwargs={"preferred_kind": "file"},
        )
    )
    registry.register(
        HeuristicRule(
            name="currency-iso4217",
            description="Field references ISO 4217 currency codes",
            provider_type="currency-iso4217",
            priority=75,
            confidence=0.78,
            matcher=_currency_matcher,
        )
    )
    registry.register(
        HeuristicRule(
            name="country-alpha2",
            description="Field references ISO country alpha-2 codes",
            provider_type="country-alpha2",
            priority=74,
            confidence=0.77,
            matcher=_country_alpha2_matcher,
        )
    )
    registry.register(
        HeuristicRule(
            name="country-alpha3",
            description="Field references ISO country alpha-3 codes",
            provider_type="country-alpha3",
            priority=73,
            confidence=0.76,
            matcher=_country_alpha3_matcher,
        )
    )
    registry.register(
        HeuristicRule(
            name="language-alpha2",
            description="Field references language or locale codes",
            provider_type="language-alpha2",
            priority=72,
            confidence=0.74,
            matcher=_language_matcher,
        )
    )


KEYWORD_CURRENCY = {"currency", "curr"}
KEYWORD_CODE = {"code", "id"}


def _currency_matcher(context: HeuristicContext) -> HeuristicResult | None:
    if context.summary.type != "string":
        return None
    tokens = set(context.tokens)
    if not tokens.intersection(KEYWORD_CURRENCY):
        return None
    if not (
        tokens.intersection(KEYWORD_CODE)
        or "iso4217" in tokens
        or _pattern_matches(context, r"^[A-Z]{3}$")
    ):
        return None
    return HeuristicResult(signals=["keyword:currency", "keyword:code"])


def _country_alpha2_matcher(context: HeuristicContext) -> HeuristicResult | None:
    if context.summary.type != "string":
        return None
    tokens = set(context.tokens)
    if "country" not in tokens:
        return None
    if _looks_like_alpha3(context):
        return None
    if not ("alpha2" in tokens or "alpha" in tokens or "code" in tokens or "iso2" in tokens):
        return None
    return HeuristicResult(signals=["keyword:country", "hint:alpha2"], confidence=0.8)


def _country_alpha3_matcher(context: HeuristicContext) -> HeuristicResult | None:
    if context.summary.type != "string":
        return None
    tokens = set(context.tokens)
    if "country" not in tokens:
        return None
    if not ("alpha3" in tokens or "iso3" in tokens or _looks_like_alpha3(context)):
        return None
    return HeuristicResult(signals=["keyword:country", "hint:alpha3"])


def _language_matcher(context: HeuristicContext) -> HeuristicResult | None:
    if context.summary.type != "string":
        return None
    tokens = set(context.tokens)
    if not ({"language", "locale", "lang"} & tokens):
        return None
    return HeuristicResult(signals=["keyword:language"])


def _pattern_matches(context: HeuristicContext, pattern: str) -> bool:
    compiled = re.compile(pattern)
    candidate = context.constraint_pattern
    return bool(candidate and compiled.search(candidate))


def _looks_like_alpha3(context: HeuristicContext) -> bool:
    return _pattern_matches(context, r"^[A-Za-z]{3}$") or _length_matches(context.summary, 3)


__all__ = [
    "HeuristicCondition",
    "HeuristicContext",
    "HeuristicMatch",
    "HeuristicRegistry",
    "HeuristicResult",
    "HeuristicRule",
    "create_default_heuristic_registry",
]
