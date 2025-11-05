# Output paths: template artifact destinations safely

> Use placeholders to structure outputs while respecting the sandbox.

## Supported placeholders

| Placeholder   | Description                                                                       |
| ------------- | --------------------------------------------------------------------------------- |
| `{model}`     | Model class name (or `combined` for aggregate files).                             |
| `{case_index}` | 1-based index of the emitted shard or fixture case.                              |
| `{timestamp}` | UTC execution timestamp (defaults to `%Y%m%dT%H%M%S`). Supports `strftime` specs. |

Examples:

```bash
pfg gen json models.py --include models.User \
  --n 3 --shard-size 1 \
  --out "artifacts/{model}/sample-{case_index}.json"

pfg gen fixtures models.py --include models.User \
  --out "tests/generated/{model}/fixtures-{timestamp:%Y%m%d}.py"
```

## Normalisation and safety

- Placeholders resolve to segments restricted to `[A-Za-z0-9._-]`. Unsafe characters are replaced with `_`.
- Paths that attempt to escape the working directory (for example `../`) are rejected with an error.
- Atomic writes ensure you either get the previous artifact or the newly completed file—never a partial.
- Directories are created automatically; ensure your user has permission to write them under the project root.

## Fixture naming tips

- Combine `{model}` with descriptive suffixes: `tests/fixtures/{model}_fixture.py`.
- Use `{timestamp:%Y%m%d}` when you want dated snapshots while keeping deterministic content via `--seed`.
- For parametrised fixtures, remember that `case_index` increments per case even when you limit models with `--include`.

See [docs/emitters.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md) for emitter-specific behaviour and atomic IO guarantees.
