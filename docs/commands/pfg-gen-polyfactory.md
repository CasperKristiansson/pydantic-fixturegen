# `pfg gen polyfactory`

## Capabilities
`pfg gen polyfactory` generates a Python module full of Polyfactory classes that delegate to fixturegen. Each exported `FooFactory` inherits from `ModelFactory`, but its `build()` method calls a shared `InstanceGenerator` with the deterministic `GenerationConfig` you specify. This lets existing Polyfactory consumers convert gradually while preserving fixturegen’s presets, relations, and seeds.

## Typical use cases
- Provide Polyfactory-style factories to teams already standardized on that API.
- Generate a module once, check it into `tests/factories/`, and import it from both pytest and CLI workflows.
- Run in watch mode during migrations from handcrafted factories to fixturegen-driven ones.

## Inputs & outputs
- **Target**: module with Pydantic models.
- **Output**: `--out` path (defaults to `polyfactory_factories.py`) or `--stdout` for piping.
- Each module includes an `InstanceGenerator` configured with the provided seed/depth/cycle/RNG options plus a helper to reseed at runtime.

## Flag reference
- `--out/-o`: destination file.
- `--stdout`: stream module to stdout.
- `--include/-i`, `--exclude/-e`: select models.
- `--seed`: embed a deterministic seed in the exported `GenerationConfig`.
- `--max-depth`, `--on-cycle`, `--rng-mode`: control recursion/cycle policies baked into the generator.
- `--watch`, `--watch-debounce`: regenerate module on changes.
- `--json-errors`: structured errors for discovery problems.

## Example workflows
### Scaffold factories into tests/factories/
```bash
pfg gen polyfactory ./app/models.py \
  --out tests/factories/polyfactory_impl.py \
  --include app.models.User,app.models.Address \
  --seed 17 --max-depth 3 --on-cycle reuse
```
Creates `UserFactory` and `AddressFactory` classes that delegate to fixturegen yet maintain the Polyfactory API.

**Sample output**
```text
[polyfactory_module_written] path=tests/factories/polyfactory_impl.py seed=17 factories=2
```

### Print to stdout for templating
```bash
pfg gen polyfactory ./app/models.py --stdout | tee tests/factories.py
```
Streams the generated module for further processing.

**Sample output**
```text
class UserFactory(ModelFactory[models.User]):
    @classmethod
    def build(cls, **kwargs):
        return _GENERATOR.generate_one(models.User, overrides=kwargs)
```

## Operational notes
- Polyfactory must be installed (`pip install pydantic-fixturegen[polyfactory]`). The command aborts with a helpful message if the dependency is missing.
- A custom module cache clearing step ensures repeated runs pick up code changes without restarting the CLI.
- When watch mode is active, the tool monitors the target module, config files, and destination path so manual edits to the output re-trigger generation.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-polyfactory)
- [Emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md)
- [Providers & delegation](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md)
