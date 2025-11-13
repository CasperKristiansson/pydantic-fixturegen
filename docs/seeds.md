# Seeds: lock in deterministic outputs

> Freeze seeds across commands to guarantee identical artifacts on every machine.

## Global seed

- Set `seed` in configuration (`pyproject.toml`, YAML, or env) to control the baseline RNG.
- CLI overrides: `--seed <int>` on `gen`, `diff`, `check`.
- When unset, the CLI derives seeds from the current time, which is not deterministic.

## Freeze file (`.pfg-seeds.json`)

Enable with `--freeze-seeds` on `pfg gen json`, `pfg gen fixtures`, or `pfg diff`.

```bash
pfg gen json ./models.py --out ./out/users.json --freeze-seeds
```

- Default path: `.pfg-seeds.json` in the project root.
- Override via `--freeze-seeds-file` or `PFG_FREEZE_SEEDS_FILE`.
- The file records per-model seeds and digests:
- Entries are keyed by the model's canonical `module.Class` name, so identifiers remain stable even if the same module was imported earlier via an internal alias.

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

## Workflow tips

- Commit the freeze file for stable CI diffs, or add it to `.gitignore` when you want environment-specific runs.
- When a model digest changes, the CLI logs `seed_freeze_stale` and regenerates a deterministic replacement.
- Missing entries are created silently on first use so quickstarts stay quiet.
- Combine with `--preset boundary` to explore edge cases while keeping reproducible seeds.
- Run `pfg diff ... --freeze-seeds` in CI to ensure outputs stay locked before merging.

Continue with [presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/presets.md) to fine-tune generation policies alongside your frozen seeds.
