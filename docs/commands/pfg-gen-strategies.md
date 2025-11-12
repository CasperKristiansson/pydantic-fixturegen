# `pfg gen strategies`

## Capabilities
`pfg gen strategies` exports a Python module that wraps `pydantic_fixturegen.hypothesis.strategy_for`. Each exported function wires the deterministic `GenerationConfig` you choose (seed, profile, recursion depth, RNG) so property-based tests can reuse the same settings as CLI generation.

## Typical use cases
- Version control Hypothesis strategies for every model without writing boilerplate.
- Embed deterministic strategies inside service repos so downstream teams can compose them.
- Stream the generated module to stdout and feed it into tools like `python -m black -` or internal template systems.
- Run in watch mode while developing new strategies.

## Inputs & outputs
- **Target**: module containing supported models (Pydantic BaseModel/RootModel, dataclasses, or TypedDicts).
- **Output**: `--out` path (defaults to `strategies.py`) or `--stdout` to print.
- Each module contains:
  - A shared `GenerationConfig` builder with the selected seed/depth/profile.
  - Helpers (for example `strategy_for_user()`) that delegate to `strategy_for` and expose docstrings describing deterministic settings.
  - A convenience `reseed()` helper for tests that want per-test seeds.

## Flag reference
- `--out/-o`: write path (default `strategies.py`).
- `--stdout`: print source to stdout instead of writing the file.
- `--include/-i`, `--exclude/-e`: glob patterns for model selection.
- `--seed`: embed a fixed seed in the exported `GenerationConfig`.
- `--strategy-profile`: `typical` (default), `edge`, or `adversarial`. Maps to the underlying Hypothesis profile.
- `--max-depth`, `--on-cycle`, `--rng-mode`: bake recursion/cycle/RNG policies into the config.
- `--watch` + `--watch-debounce`: regenerate automatically when target files change.
- `--json-errors`: structured diagnostics for discovery failures.

## Example workflows
### Export adversarial strategies to tests/strategies.py
```bash
pfg gen strategies ./app/models.py \
  --out tests/strategies/test_models.py \
  --include app.models.User,app.models.Order \
  --strategy-profile adversarial --seed 321 \
  --max-depth 4 --on-cycle reuse
```
Creates a module ready for `pytest` that exposes `user_strategy()` and `order_strategy()` helpers.

**Sample output**
```text
[strategies_written] path=tests/strategies/test_models.py profile=adversarial seed=321
exports:
  user_strategy -> app.models.User
  order_strategy -> app.models.Order
```

### Stream to stdout during CI scaffolding
```bash
pfg gen strategies ./app/models.py --stdout | black -q - > tests/strategies.py
```
Integrates with formatting pipelines without touching disk first.

**Sample output**
```text
from pydantic_fixturegen.hypothesis import strategy_for
...
def user_strategy():
    return strategy_for(models.User, config=_GEN_CONFIG)
```

## Operational notes
- The command imports the target module to introspect model classes; ensure optional dependencies are installed or run `pfg list --ast` first to confirm import safety.
- When watch mode is enabled the generator observes the target module tree plus the output path so that both source edits and manual file touches trigger reruns.
- If no models match the include/exclude filters, fixturegen raises `DiscoveryError` to prevent writing an empty module.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-strategies)
- [Strategies deep dive](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/strategies.md)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
