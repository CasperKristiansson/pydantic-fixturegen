# Providers: extend data generation

> Register new providers or override defaults without touching core code.

## Provider registry basics

- Core providers cover numbers, strings (with optional regex support), collections, temporal values, and identifiers.
- Providers live in `pydantic_fixturegen.core.providers` and are loaded through a `ProviderRegistry`.
- Plugins register new providers via Pluggy and can override defaults selectively.

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
- Use `pfg_modify_strategy` (see [strategies](./strategies.md)) when you need to tweak probabilities or shape decisions instead of replacing providers.
- Validate new providers by running `pfg gen explain` to confirm they appear in the strategy tree.
- Ship unit tests that cover provider edge cases; the project uses Faker extensively, so rely on cascaded seeds to stay deterministic.

Continue with [emitters](./emitters.md) to control artifact output once providers deliver their data.
