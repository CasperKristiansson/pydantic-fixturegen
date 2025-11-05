# Emitters: JSON, pytest fixtures, and schema outputs

> Understand how artifacts are written so you can tune formatting and metadata.

## JSON / JSONL emitter

- Uses `emit_json_samples` to stream data into one or many files.
- Supports JSON arrays or JSONL depending on `--jsonl`.
- Metadata banner (when indenting) includes `seed`, `version`, and `digest`.
- Sharding uses zero-padded indices (default width `5`) and honours templates.
- Optional `orjson` extra speeds up serialization; falls back to stdlib JSON otherwise.
- Trailing newlines are enforced so diffs stay clean.
- Atomic writes ensure each shard is written to a temp file and moved into place.

### Key options

| Option           | Effect                                              |
| ---------------- | --------------------------------------------------- |
| `--n`            | Number of records to emit.                          |
| `--jsonl`        | Emit newline-delimited JSON.                        |
| `--indent`       | Pretty-print JSON arrays and enable metadata banner. |
| `--shard-size`   | Split records across multiple files.                |
| `--orjson`       | Toggle the optional `orjson` encoder.               |
| `--freeze-seeds` | Maintain per-model seeds in `.pfg-seeds.json`.      |

## Pytest fixture emitter

- Builds deterministic fixture modules with deduped imports and Ruff/Black-friendly formatting.
- Banner includes generator version, seed, style, scope, return type, case count, and model list.
- Styles: `functions`, `factory`, `class`. Return types: `model`, `dict`.
- Scope defaults to `function`; adjust via config or `--scope`.
- Atomic writes via `write_atomic_text` protect against partial files.
- Incorporates constraint summaries into metadata when generation hits boundaries.

### Tuning knobs

- `--style`, `--scope`, `--cases`, `--return-type`, `--p-none`.
- When using per-model seeds, combine with `--freeze-seeds` to populate metadata.
- For factory/class styles, helper names are generated deterministically to avoid collisions.

## Schema emitter

- Calls `model_json_schema()` for each model and writes sorted JSON.
- Supports combined outputs (`schema/{model}.json`) or aggregated dictionaries.
- `--indent` prettifies schema files; `0` or `None` compacts output.
- Writes a trailing newline for stability.

## Watch mode compatibility

- All emitters respect `--watch` and `--watch-debounce`.
- The CLI listens for Python, TOML, and YAML changes beneath the working directory.
- Combine watch mode with `--freeze-seeds` to ensure regenerated artifacts remain deterministic.

## Troubleshooting emitters

- Missing files? Ensure `--out` resolves inside the working directory; sandbox will block escapes.
- Fixture scopes causing reuse issues? Switch to `--scope function` or increase `--cases`.
- JSON diffs noisy? Lower `--indent` or enable `--jsonl` to minimise whitespace differences.
- Schema missing updates? Check that models expose `model_json_schema()` and rerun `pfg check` to validate destinations.

Review [output paths](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md) for templating details and [logging](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/logging.md) to capture emitter events.
