# CLI: drive generation from commands

> Learn every command, flag, and default so you can script generation with confidence.

## Global options

```bash
pfg --verbose       # repeat -v to increase verbosity (info → debug)
pfg --quiet         # repeat -q to reduce output (info → warning → error → silent)
pfg --log-json      # emit structured JSON logs; combine with jq for CI parsing
```

You can append `-- --help` after any proxy command to view native Typer help because `pfg` forwards arguments to sub-apps.

## `pfg list`

```bash
pfg list ./models.py --include pkg.User --public-only
```

- Lists fully-qualified model names discovered via AST and safe-import by default.
- Use `--ast` to disable imports, `--hybrid` to combine AST with sandbox inspection, or `--timeout` / `--memory-limit-mb` to tune sandbox guards.
- `--json-errors` prints machine-readable payloads with error code `20`.

## `pfg gen`

`gen` hosts multiple subcommands. Inspect them with `pfg gen -- --help`.

### `pfg gen json`

```bash
pfg gen json ./models.py \
  --out ./out/users.json \
  --include pkg.User \
  --n 10 \
  --jsonl \
  --indent 0 \
  --orjson \
  --shard-size 1000 \
  --seed 42 \
  --freeze-seeds \
  --preset boundary
```

- `--out` is required and supports templates (`{model}`, `{case_index}`, `{timestamp}`).
- Control volume with `--n` (records) and `--shard-size` (records per file).
- Switch encoding with `--jsonl`, `--indent`, `--orjson/--no-orjson`.
- Determinism helpers: `--seed`, `--freeze-seeds`, `--freeze-seeds-file`, `--preset`.
- Observability: `--json-errors`, `--watch`, `--watch-debounce`, `--now`.

### `pfg gen fixtures`

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_models.py \
  --style factory \
  --scope module \
  --cases 3 \
  --return-type dict \
  --p-none 0.2 \
  --seed 42
```

- `--out` is required and can use templates.
- `--style` controls structure (`functions`, `factory`, `class`).
- `--scope` sets fixture scope; `--cases` parametrises templates.
- `--return-type` chooses between returning the model or its dict representation.
- Determinism flags mirror `gen json`.

### `pfg gen schema`

```bash
pfg gen schema ./models.py --out ./schema --include pkg.User
```

- Requires `--out` and writes JSON Schema files atomically.
- Combine with `--include`/`--exclude`, `--json-errors`, `--watch`, and `--now`.

### `pfg gen explain`

```bash
pfg gen explain ./models.py --tree --max-depth 2 --include pkg.User
```

- `--tree` prints ASCII strategy diagrams.
- `--json` emits structured data suitable for tooling.
- Limit depth with `--max-depth`, filter models with `--include`/`--exclude`.
- Use `--json-errors` for machine-readable failures.

## `pfg diff`

```bash
pfg diff ./models.py \
  --json-out out/users.json \
  --fixtures-out tests/fixtures/test_models.py \
  --schema-out schema \
  --show-diff
```

- Regenerates artifacts in-memory and compares them with existing files.
- Writes JSON summaries when you pass output paths.
- `--show-diff` streams unified diffs to stdout.
- Determinism helpers: `--seed`, `--freeze-seeds`.

## `pfg check`

```bash
pfg check ./models.py --json-errors --fixtures-out /tmp/fixtures.py
```

- Validates configuration, discovery, and emitter destinations without writing artifacts.
- Mirrors `diff` output flags, including `--json-out`, `--fixtures-out`, and `--schema-out`.
- Use it in CI to block invalid configs before generation.

## `pfg init`

```bash
pfg init \
  --pyproject-path pyproject.toml \
  --yaml \
  --yaml-path config/pydantic-fixturegen.yaml \
  --seed 42 \
  --union-policy weighted \
  --enum-policy random \
  --json-indent 2 \
  --pytest-style functions \
  --pytest-scope module
```

- Scaffolds configuration files and optional fixture directories.
- Accepts `--no-pyproject` if you only want YAML.
- Adds `.gitkeep` inside `tests/fixtures/` unless you pass `--no-fixtures-dir`.

## `pfg plugin`

```bash
pfg plugin new acme-colorizer \
  --namespace acme.plugins \
  --distribution acme-pfg-colorizer \
  --entrypoint acme-colorizer \
  --directory ./acme-colorizer
```

- Generates a pluggy provider project with `pyproject.toml`, README, tests, and GitHub Actions workflow.
- `--namespace` builds a nested package layout (for example `src/acme/plugins/acme_colorizer`).
- Override packaging metadata with `--distribution`, `--entrypoint`, `--description`, and `--author`.
- Use `--force` to overwrite existing files when iterating on a scaffold in-place.

## `pfg doctor`

```bash
pfg doctor ./models.py --fail-on-gaps 0 --json-errors
```

- Audits coverage gaps (fields without providers), risky imports, and sandbox findings.
- Use `--fail-on-gaps` to turn warnings into non-zero exits.
- Combine with `--include`/`--exclude` to focus on specific models.

## `pfg schema`

```bash
pfg schema config --out schema/config.schema.json
```

- Dumps JSON Schemas describing configuration or model outputs.
- The `config` subcommand wraps the schema bundled under `pydantic_fixturegen/schemas/config.schema.json`.

## Tips for scripting

- Append `--json-errors` anywhere you need machine-readable results; check exit codes for CI gating.
- Use `--now` when you want reproducible “current time” values in generated data.
- `--preset boundary` or `--preset boundary-max` applies opinionated strategies; combine with explicit overrides to fine-tune probability.
- When piping commands, pass `--` before flags for subcommands to avoid Typer proxy conflicts.

Continue to [output paths](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md) for templating and [logging](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/logging.md) for structured events that pair with automation.
