# `pfg polyfactory migrate`

Polyfactory adopters can inventory existing `ModelFactory` overrides and auto-generate fixturegen config snippets instead of rewriting factories by hand. The command inspects every discovered factory, compares its field overrides to fixturegen's current provider plan, and emits actionable reports plus `[tool.pydantic_fixturegen.overrides]` entries.

## Highlights

- Detects `Use`, `Ignore`, `Require`, `PostGenerated`, and literal field overrides defined on Polyfactory classes.
- Shows the provider/heuristic fixturegen would use today so you can decide whether an override is still required.
- Translates supported overrides into fixturegen config that relies on helper adapters (`invoke_use`, `invoke_post_generate`) so callables keep working.
- Flags unsupported constructs (lambdas, non-serializable values, nested factories, etc.) so you know where manual work remains.

## Usage

```bash
pfg polyfactory migrate ./app/models.py \
  --include app.models.User \
  --factory-module app.factories \
  --overrides-out overrides-polyfactory.toml
```

### Key options

| Flag | Description |
| ---- | ----------- |
| `TARGET` | Path to a Python module containing Pydantic models. Required. |
| `--include/-i`, `--exclude/-e` | Glob filters (comma-separated) applied before discovery. |
| `--factory-module/-m` | Extra module(s) to scan for Polyfactory factories (repeatable, mirrors `[polyfactory].modules`). |
| `--format/-f` | `table` (default) for a readable report or `json` for machine processing. |
| `--overrides-out` | Write translated overrides to a TOML file that can be merged into `pyproject.toml`. |

The command loads the current configuration (presets, heuristics, provider defaults, etc.) so the fixturegen provider columns in the report match what your next `pfg gen ...` run would use.

## Sample table output

```text
Model: app.models.User
Factory: app.factories.UserFactory
  - slug [translated]
      Polyfactory: Use(slugify)
      Fixturegen: string:slug [heuristic:slug-format]
      Override: {"factory": "pydantic_fixturegen.polyfactory_support.migration_helpers:invoke_use", "factory_args": ["app.factories:slugify", ["user-"], {}]}
  - alias [translated]
      Polyfactory: Ignore()
      Fixturegen: string
      Override: {"ignore": true}
  - legacy_id [manual]
      Polyfactory: Use(<lambda>)
      Fixturegen: string
      Note: callable could not be resolved
```

With `--format json` the same data is emitted as structured JSON so you can feed it into custom tooling or dashboards.

## Generated overrides

Whenever translation succeeds the command aggregates a `[tool.pydantic_fixturegen.overrides]` snippet. The helper adapters live in `pydantic_fixturegen.polyfactory_support.migration_helpers` and handle bridging fixturegen's override API with Polyfactory's callable semantics.

```toml
[tool.pydantic_fixturegen.overrides."app.models.User".slug]
factory = "pydantic_fixturegen.polyfactory_support.migration_helpers:invoke_use"
factory_args = ["app.factories:slugify", ["user-"], {}]

[tool.pydantic_fixturegen.overrides."app.models.User".alias]
ignore = true
```

The adapters expect importable callable paths (either `module:attr` or dotted module paths). If a callable cannot be resolved (lambdas, closures, dynamically generated functions), the report lists it under the "manual" bucket so you can decide how to recreate the behaviour.

## Workflow

1. Run `pfg polyfactory migrate` against your project module.
2. Address any "manual" notes in the report (rewrite lambdas, export helper functions, etc.).
3. Merge the generated TOML snippet into `[tool.pydantic_fixturegen.overrides]`.
4. Re-run `pfg coverage report` / `pfg doctor` or spot-check with `pfg gen explain` to validate that fixturegen now honours the overrides.
5. Remove the original Polyfactory factories when you're satisfied with the parity.

> ℹ️  The command requires the `polyfactory` extra (`pip install "pydantic-fixturegen[polyfactory]"`). On Python 3.14+ you must opt in via `PFG_POLYFACTORY__ALLOW_PY314=1` because upstream Polyfactory still depends on Pydantic v1 APIs.
