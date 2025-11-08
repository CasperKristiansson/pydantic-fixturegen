# Providers: extend data generation

> Register new providers or override defaults without touching core code.

## Provider registry basics

- Core providers cover numbers, strings (with optional regex support), collections, temporal values, and identifiers.
- Providers live in `pydantic_fixturegen.core.providers` and are loaded through a `ProviderRegistry`.
- Plugins register new providers via Pluggy and can override defaults selectively.
- A heuristic rule engine inspects field names, aliases, constraints, and metadata to map common shapes (emails, slugs, country/language codes, filesystem paths, etc.) onto richer providers automatically; see [heuristic settings](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#heuristic-settings) for opt-out controls.
- When the [`polyfactory`](https://pypi.org/project/polyfactory/) extra is installed and `[polyfactory]` keeps `prefer_delegation = true`, fixturegen auto-registers any `ModelFactory` subclasses it finds as model-level delegates so you can keep bespoke Polyfactory logic without touching providers manually.

## Scaffold plugin projects

Spin up a ready-to-publish skeleton with:

```bash
pfg plugin new acme-colorizer --namespace acme.plugins
```

The scaffold includes entry-point wiring, sample providers, pytest coverage, and a GitHub Actions workflow so teams can start iterating immediately.

## Register custom providers

Implement `pfg_register_providers` in a module reachable by entry points or manual registration.

```python
# acme_fixtures/providers.py
from pydantic_fixturegen.plugins.hookspecs import hookimpl

class EmailMaskerPlugin:
    @hookimpl
    def pfg_register_providers(self, registry):
        registry.register("email", my_email_provider)

plugin = EmailMaskerPlugin()
```

Expose the plugin:

```toml
[project.entry-points."pydantic_fixturegen"]
acme_email_masker = "acme_fixtures.providers:plugin"
```

The registry receives your provider before strategies are built, allowing the CLI and API to use it immediately.

## Manual registration

When you want explicit control (for example in scripts), register plugins directly:

```python
from pydantic_fixturegen.core.providers import create_default_registry
from acme_fixtures.providers import plugin

registry = create_default_registry(load_plugins=False)
registry.register_plugin(plugin)
```

- Set `load_plugins=False` to disable automatic entry point loading.
- Call `registry.register("name", callable)` when you need ad-hoc providers without a plugin object.

## Provider best practices

- Keep providers pure functions. They should accept Faker instances and field summaries, returning deterministic values that respect seeds.
- Respect configuration overrides (`p_none`, union/enum policies) by reading the field summary rather than global state.
- Use `pfg_modify_strategy` (see [strategies](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/strategies.md)) when you need to tweak probabilities or shape decisions instead of replacing providers.
- Validate new providers by running `pfg gen explain` to confirm they appear in the strategy tree.
- Ship unit tests that cover provider edge cases; the project uses Faker extensively, so rely on cascaded seeds to stay deterministic.

## Built-in identifier providers

Typed identifier fields now have dedicated providers that keep seeded runs reproducible while generating realistic values:

- `EmailStr`, `AnyUrl`/`HttpUrl`, `PaymentCardNumber`, and `uuid.UUID` map to the identifier provider family.
- `SecretStr` and `SecretBytes` respect length constraints derived from the field summary and fall back to `identifiers.secret_str_length` / `identifiers.secret_bytes_length`.
- IP address/network/interface types rely on deterministic RNG output so fixture diffs stay stable.

Tweak behaviour through the `[tool.pydantic_fixturegen.identifiers]` section documented in [configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#identifier-settings). Strategies automatically pass the resolved config to providers, so CLI, API, and emitter workflows all honour the same settings.

> **Extras**: `EmailStr` support requires the optional `email` extra, while `PaymentCardNumber` relies on the `payment` extra that pulls in `pydantic-extra-types`.

## Slug provider

- String fields typed as `SlugStr` (from `pydantic-extra-types`) or heuristically flagged as slugs now use a dedicated provider that emits lowercase, hyphenated tokens respecting `min_length`/`max_length` constraints.
- The provider reuses Faker's `slug()` method under deterministic seeding, so fixture diffs remain stable across runs.
- Heuristic rules cover plain `str` annotations named `slug`, `slug_text`, etc. and can be disabled via `[heuristics]` if you prefer to wire policies manually.

## `pydantic-extra-types` support

- When the [`pydantic-extra-types`](https://pypi.org/project/pydantic-extra-types/) package is installed, fixturegen automatically registers providers for common shapes such as `Color`, `Coordinate`, `Country*`, `DomainStr`, `PhoneNumber`, `SemanticVersion`, `S3Path`, `ULID`, and the pendulum date/time classes.
- Providers emit deterministic but realistic payloads (for example, hex colours, ISO 4217 currency codes, or MongoDB object IDs) so seeded runs stay stable across CLI, API, and emitter workflows.
- The registry only activates providers for types whose modules can be imported; missing optional dependencies simply skip registration without failing the run.
- `pfg doctor` now flags models that reference `pydantic-extra-types` annotations when the matching provider is unavailable, helping you decide whether to install the extra or override the field manually.

## Built-in path providers

- `pathlib.Path`, `pydantic.DirectoryPath`, and `pydantic.FilePath` fields now receive seeded paths that mimic Windows, macOS, or generic POSIX conventions.
- Paths are sanitised with the same helpers used for templated outputs, so generated segments stay within `[A-Za-z0-9._-]` even when lengths are constrained.
- Configure targets through `[tool.pydantic_fixturegen.paths]` or the `PFG_PATHS__*` environment overrides documented in [configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#path-settings). Per-model glob patterns let you point specific models at different OS flavours without impacting the rest of the run.
- Providers accept explicit Faker/random generators from strategies, so `pfg diff`, emitters, and the Python API all honour the same deterministic paths.

Continue with [emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md) to control artifact output once providers deliver their data.
