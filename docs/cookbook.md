# Cookbook: Ship deterministic data with focused recipes

> Apply task-sized patterns for scaling JSON, tuning pytest fixtures, freezing seeds, extending providers, and inspecting explain trees.

## Recipe 1 — Shard massive JSON/JSONL outputs

You need predictable files when generating thousands of records.

```bash
pfg gen json ./models.py \
  --include app.models.User \
  --n 20000 \
  --jsonl \
  --shard-size 1000 \
  --out "artifacts/{model}/shard-{case_index}.jsonl" \
  --indent 0 \
  --orjson
```

- Use `--jsonl` to stream one record per line.
- `--shard-size` controls how many records land in each file; a final shard uses the remaining count.
- `--orjson` activates the optional high-performance encoder (`pip install 'pydantic-fixturegen[orjson]'`).
- Template placeholders keep shards organised per model and shard index.

Validate the emitters by checking the metadata banner for `seed`, `version`, and `digest`.

## Recipe 2 — Adjust pytest fixture style and scope

Switch fixture ergonomics without editing generated code.

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_models.py \
  --style factory \
  --scope session \
  --cases 5 \
  --return-type dict
```

- `--style` accepts `functions`, `factory`, or `class`. Pick the format that matches your test suite guidelines.
- `--scope` accepts `function`, `module`, or `session`. Choose wider scopes to reuse expensive models.
- `--cases` parametrises fixtures with deterministic data; indexes become `request.param`.
- `--return-type dict` converts fixtures into dictionaries for JSON-like assertions.

Pair this recipe with Ruff’s formatter or `pytest --fixtures` to verify output.

## Recipe 3 — Freeze seeds for reproducible CI diffs

Keep generated data stable across machines by freezing per-model seeds.

```bash
pfg gen json ./models.py \
  --out ./out/users.json \
  --freeze-seeds \
  --freeze-seeds-file .pfg-seeds.json
```

- The freeze file stores model digests and derived seeds.
- When digests change, the CLI prints `seed_freeze_stale` warnings so you can review updated fixtures.
- Combine with `--preset boundary` to explore edge cases while staying deterministic.

Review the freeze file:

```json
{
  "version": 1,
  "models": {
    "app.models.User": {
      "seed": 412067183,
      "model_digest": "8d3db06f…"
    }
  }
}
```

Commit the file to source control when you want cross-team consistency.

## Recipe 4 — Register a custom provider via Pluggy

Extend generation without forking core code.

```python
# plugins/nickname_boost.py
from pydantic import BaseModel
from pydantic_fixturegen.plugins.hookspecs import hookimpl

class NicknameBoost:
    @hookimpl
    def pfg_modify_strategy(self, model: type[BaseModel], field_name: str, strategy):
        if model.__name__ == "User" and field_name == "nickname":
            return strategy.model_copy(update={"p_none": 0.1})
        return None

plugin = NicknameBoost()
```

Register the plugin and run generation:

```python
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.plugins.loader import register_plugin

from plugins.nickname_boost import plugin

registry = create_default_registry(load_plugins=False)
register_plugin(registry, plugin)
```

- The hook returns a modified strategy for the matching field; return `None` to fall back to defaults.
- Use entry points under `pydantic_fixturegen` for discovery in packages.
- Inspect the effect with `pfg gen explain --tree`.

## Recipe 5 — Debug strategies with explain trees

Expose provider choices to understand constraint handling.

```bash
pfg gen explain ./models.py --tree --max-depth 2 --include app.models.User
```

- `--tree` prints an indented diagram showing providers, presets, and policy tweaks.
- `--json` emits a machine-readable payload suitable for CI or dashboards.
- `--max-depth` limits recursion when dealing with large nested models.

Use `--json` together with jq for targeted checks:

```bash
pfg gen explain ./models.py --json | jq '.models["app.models.User"].fields.nickname'
```

You see probability adjustments, active presets, and provider names, making policy mismatches easy to spot.

## Recipe 6 — Assert artifacts with pytest snapshots

Lean on the built-in pytest helper to keep JSON, fixtures, or schema outputs in sync with snapshots.

```python
from pathlib import Path

from pydantic_fixturegen.testing import JsonSnapshotConfig


def test_user_snapshot(pfg_snapshot):
    config = JsonSnapshotConfig(out=Path("tests/snapshots/users.json"), indent=2)
    pfg_snapshot.assert_artifacts(
        target="./models.py",
        json=config,
        include=["app.models.User"],
    )
```

- The `pfg_snapshot` fixture ships via the `pytest11` entry point; no manual plugin registration needed.
- Pass one or more configs (`JsonSnapshotConfig`, `FixturesSnapshotConfig`, `SchemaSnapshotConfig`) to cover the artifacts you want to track.
- Run `pytest --pfg-update-snapshots=update` or set `PFG_SNAPSHOT_UPDATE=update` to refresh snapshots when behaviour changes; by default the helper fails with the unified diff from `pfg diff`.
- For one-off overrides, tag a test with `@pytest.mark.pfg_snapshot_config(update="update", timeout=10)` to opt into updates or tweak sandbox limits without affecting neighbouring tests.
- All `pfg diff` knobs are available—`include`, `exclude`, `seed`, `preset`, `freeze_seeds`, etc.—so update determinism is preserved.

Use this in tandem with Recipe 3 (freeze seeds) to keep fixtures stable across machines.

## Recipe 7 — Mix Faker locales per model

Reflect regional datasets by mapping models or fields to specific locales.

```toml
[tool.pydantic_fixturegen.locales]
"app.models.Customer.*" = "de_DE"
"app.models.Customer.email" = "en_GB"
```

- Patterns accept glob wildcards or regex (`re:` prefix).
- Field matches override broader model patterns, so the example keeps German defaults while forcing `.email` to the UK locale.
- To blanket a model you can omit the trailing `.*` (`"app.models.Customer"`) or use the bare class name (`"Customer"`).
- Combine with `pfg gen json --seed 42` to verify deterministic outputs across locales.
- See the configuration reference at [docs/configuration.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#locale-overrides) for deeper details and validation rules.

## Recipe 8 — Generate NumPy arrays safely

Avoid runaway allocations by capping shapes and dtypes globally.

```toml
[tool.pydantic_fixturegen.arrays]
max_ndim = 2
max_side = 4
max_elements = 16
dtypes = ["float32", "int16"]
```

- Requires the `numpy` extra (`pip install pydantic-fixturegen[numpy]`).
- Fields annotated as `numpy.ndarray` or `numpy.typing.NDArray[...]` automatically use these caps.
- Deterministic seeds flow through `SeedManager.numpy_for`, so array contents remain stable across runs.
- Combine with field policies when you need to override other behaviours (for example `p_none`).

## Recipe 9 — Enforce privacy profiles per environment

Use the built-in privacy bundles when you need obviously synthetic datasets in CI but richer identifiers locally.

```bash
pfg gen json ./models.py --out snapshots/users.json --profile pii-safe
pfg diff ./models.py --json-out snapshots/users.json --profile realistic
```

- `pii-safe` masks emails/URLs/IPs with reserved example values and makes optional PII fields far more likely to be `None`.
- `realistic` keeps optional contact fields populated and re-enables full identifier distributions.
- Set `[tool.pydantic_fixturegen].profile = "pii-safe"` for CI defaults, then override locally with `PFG_PROFILE=realistic` or `--profile realistic`.

## More plays

- Automate regeneration with watch mode: `pfg gen fixtures ... --watch`.
- Diff outputs before committing: `pfg diff models.py --fixtures-out tests/fixtures/test_models.py --show-diff`.
- Harden imports by running `pfg doctor` with `--fail-on-gaps 0` and review the structured report.
