# Strategies: tweak how fields are generated

> Modify policies and providers per field without rewriting emitters.

## Strategy builder overview

- `StrategyBuilder` inspects model fields, summarises constraints, and assigns providers.
- Union fields become `UnionStrategy` instances with multiple choices and a policy (`first`, `random`, or `weighted`).
- Optional fields inherit `p_none` probabilities from configuration or presets.
- Enum fields use the `enum.static` provider by default.

## Modify strategies with plugins

Implement `pfg_modify_strategy` to adjust probabilities or swap providers.

```python
# plugins/nickname_strategy.py
from pydantic import BaseModel
from pydantic_fixturegen.plugins.hookspecs import hookimpl

class NicknameTweaks:
    @hookimpl
    def pfg_modify_strategy(self, model: type[BaseModel], field_name: str, strategy):
        if model.__name__ == "User" and field_name == "nickname":
            return strategy.model_copy(update={"p_none": 0.1})
        return None

plugin = NicknameTweaks()
```

- Return a new `Strategy` to override attributes; return `None` to keep the original.
- Use `model_copy` (dataclass copy) to avoid mutating shared state.
- Register the plugin via entry points or manual registry registration (see [providers](./providers.md)).

## Common adjustments

- Increase `p_none` for optional fields that should appear sparingly.
- Swap providers by updating `provider_ref`/`provider_name` to point at custom implementations.
- Override `enum_policy` to `random` when exploring edge cases.
- Alter `provider_kwargs` to tune providers that accept additional parameters.

## Validate your changes

- Run `pfg gen explain --tree` to confirm new strategies appear in the output.
- Combine with `--preset boundary` to ensure presets and custom strategies interact correctly.
- Use `pfg doctor` to verify no coverage gaps remain after replacing providers.

Strategies work hand-in-hand with [emitters](./emitters.md), which consume provider output to write artifacts.
