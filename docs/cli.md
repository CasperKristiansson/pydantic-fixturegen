# CLI: drive generation from commands

> Learn every command, flag, and default so you can script generation with confidence.

## Global options

```bash
pfg --verbose       # repeat -v to increase verbosity (info → debug)
pfg --quiet         # repeat -q to reduce output (info → warning → error → silent)
pfg --log-json      # emit structured JSON logs; combine with jq for CI parsing
```

You can append `-- --help` after any proxy command to view native Typer help because `pfg` forwards arguments to sub-apps.

## Command map (cheat sheet)

| Command | Purpose |
| ------- | ------- |
| `pfg list` | Discover models via AST/safe-import hybrids. |
| `pfg gen json` / `dataset` / `fixtures` / `schema` | Emit JSON/JSONL, CSV/Parquet/Arrow, pytest fixtures, or JSON Schema. |
| `pfg gen seed sqlmodel|beanie` | Populate SQLModel/SQLAlchemy or Beanie/MongoDB databases. |
| `pfg gen examples` | Inject deterministic examples into OpenAPI specs. |
| `pfg gen strategies` | Export Hypothesis strategies wired to `strategy_for`. |
| `pfg gen explain` | Visualise generation plans (tree or JSON). |
| `pfg gen polyfactory` | Scaffold Polyfactory classes that delegate to fixturegen. |
| `pfg fastapi smoke` / `serve` | Generate FastAPI smoke tests or launch a deterministic mock server. |
| `pfg anonymize` | Rewrite JSON/JSONL payloads via rule-driven strategies. |
| `pfg diff` / `check` / `doctor` | Compare artefacts, validate configs, audit coverage. |
| `pfg snapshot verify/write` | Verify or refresh stored snapshots outside pytest. |
| `pfg lock` / `verify` | Record and enforce coverage manifests in CI. |
| `pfg init` / `plugin` | Scaffold config files or custom pluggy providers. |

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
- Relations: declare cross-model links with `--link Order.user_id=User.id` and co-generate related records with `--with-related User,Item` (each JSON sample becomes a dict keyed by model name).
- TypeAdapter mode: pass `--type "list[EmailStr]"` to evaluate a Python type expression via `TypeAdapter` without discovering a module first. Expressions can reference types from the target module when you also pass the module path, but you cannot combine `--type` with `--link`, `--with-related`, or `--freeze-seeds`, and watch mode requires a module path so imports can be refreshed.
- Validator enforcement: add `--respect-validators` to retry on model/dataclass validator failures and `--validator-max-retries` to cap the extra attempts.
- Privacy bundles: `--profile pii-safe` masks identifiers; `--profile realistic` restores richer distributions.
- Observability: `--json-errors`, `--watch`, `--watch-debounce`, `--now`.

### `pfg gen dataset`

```bash
pfg gen dataset ./models.py \
  --out ./warehouse/users.csv \
  --format parquet \
  --compression zstd \
  --n 1000000 \
  --shard-size 200000 \
  --include pkg.User \
  --seed 7 \
  --preset boundary-max
```

- `--format` selects `csv`, `parquet`, or `arrow`. Each honours deterministic seeds and shares the same generation pipeline as `gen json`.
- CSV output streams line-by-line (optionally via `--compression gzip`), while Parquet and Arrow use PyArrow writers; install the `[dataset]` extra or `pyarrow` to enable columnar formats.
- `--shard-size` splits high-volume runs across multiple files without buffering the entire dataset in memory; templates with `{case_index}` apply per shard exactly like `gen json`.
- Cycle metadata is preserved via the `__cycles__` column so downstream checks can reason about recursion heuristics.
- Determinism helpers mirror `gen json`: `--seed`, `--freeze-seeds`, `--preset`, `--profile`, `--now`, `--respect-validators`, `--validator-max-retries`, `--max-depth`, `--on-cycle`, `--rng-mode`.
- Observability: `--json-errors`, `--watch`, `--watch-debounce`, and relation links via `--link source.field=target.field` stay consistent with other emitters.

### `pfg gen seed`

```bash
pfg gen seed sqlmodel ./models.py \
  --database sqlite:///seed.db \
  --include app.User \
  --n 100 \
  --create-schema \
  --batch-size 25 \
  --truncate

pfg gen seed beanie ./models.py \
  --database mongodb://localhost:27017/app \
  --include app.Account \
  --cleanup
```

- `sqlmodel` seeds SQLModel/SQLAlchemy tables via transactional sessions. Use `--database` for the engine URL, `--create-schema` to run `SQLModel.metadata.create_all()`, `--batch-size` to control flush size, `--truncate` to clear existing rows, `--rollback` to run rollback-only transactions, and `--dry-run` to log payloads without touching the database.
- `beanie` streams deterministic documents into MongoDB; `--cleanup` deletes inserted docs at the end so fixtures can reuse the same collections. Both commands honour `--seed`, `--freeze-seeds`, `--preset`, `--profile`, `--link`, `--with-related`, `--respect-validators`, `--validator-max-retries`, `--max-depth`, `--on-cycle`, and `--rng-mode`.
- Database URLs are allowlisted by prefix (`sqlite://` and `mongodb://` by default). Pass `--allow-url prefix` (repeatable) when you really want to point at another environment.
- Install the `[seed]` extra or the narrower `[sqlmodel]` / `[beanie]` extras to pull in SQLModel/SQLAlchemy, Beanie, Motor, and mongomock for local testing.

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
- Determinism flags mirror `gen json`, and `--profile` applies the same privacy bundles before fixture emission.
- Relations: `--link Order.user_id=User.id` keeps fixtures consistent and `--with-related User` ensures the related fixtures are emitted in the same module when you need bundles.
- Validator enforcement mirrors `gen json`: `--respect-validators` applies bounded retries and `--validator-max-retries` adjusts the ceiling.

### `pfg gen schema`

```bash
pfg gen schema ./models.py --out ./schema --include pkg.User
```

- Requires `--out` and writes JSON Schema files atomically.
- Combine with `--include`/`--exclude`, `--json-errors`, `--watch`, `--now`, and `--profile` when you want schema discovery to evaluate a specific privacy profile.

### `pfg gen examples`

```bash
pfg gen examples openapi.yaml \
  --route "GET /users" \
  --route "POST /orders" \
  --out openapi.examples.yaml \
  --seed 7 \
  --freeze-seeds
```

- Requires the `openapi` extra so `datamodel-code-generator` and PyYAML are available.
- Ingests an OpenAPI 3.x spec, isolates the referenced schemas per route, and injects deterministic `example` blocks into responses and request bodies.
- `--route` is repeatable; omit it to process every route/component. Use `--include`/`--exclude` for fine-grained schema control.
- Determinism helpers mirror `gen json`: `--seed`, `--freeze-seeds`, `--profile`, `--respect-validators`, `--validator-max-retries`, `--max-depth`, `--on-cycle`, `--rng-mode`.
- Combine with `pfg gen openapi` JSON emission to keep SDK examples and test fixtures aligned without hand-crafted payloads.

### `pfg gen explain`

```bash
pfg gen explain ./models.py --tree --max-depth 2 --include pkg.User
```

- `--tree` prints ASCII strategy diagrams.
- `--json` emits structured data suitable for tooling.
- Limit depth with `--max-depth`, filter models with `--include`/`--exclude`.
- Use `--json-errors` for machine-readable failures.

### `pfg gen polyfactory`

```bash
pfg gen polyfactory ./models.py --out tests/polyfactory_factories.py --seed 11 --max-depth 4
```

- Emits a Python module full of `ModelFactory` subclasses whose `build()` methods delegate to a shared `InstanceGenerator`, so existing Polyfactory consumers can migrate gradually while keeping deterministic fixturegen data.
- Supports `--include`/`--exclude`, `--seed`, `--max-depth`, `--on-cycle`, `--rng-mode`, and `--watch` just like other `gen` subcommands. Pass `--stdout` to stream the scaffold elsewhere.
- Pair with the `[polyfactory]` config block: the CLI respects `prefer_delegation` and automatically registers any factories it exported the next time you run `gen json`, `gen fixtures`, or the FastAPI commands.

### `pfg gen strategies`

```bash
pfg gen strategies ./models.py \
  --include models.User \
  --out tests/strategies/test_users.py \
  --seed 123 \
  --strategy-profile edge \
  --stdout
```

- Exports Hypothesis strategies built on `pydantic_fixturegen.hypothesis.strategy_for` so property-based tests reuse the same configuration (seed, RNG mode, cycle policy, presets) as the CLI.
- `--strategy-profile` toggles value distributions (`typical`, `edge`, `adversarial`); combine with `--preset` and `--profile` for complete control.
- Add `--stdout` to stream the module directly into other tooling, or point `--out` at a Python file to commit alongside your tests.
- The generated module includes helper functions to reseed strategies on demand, and each exported symbol carries docstrings describing the deterministic settings used.

## `pfg anonymize`

```bash
pfg anonymize \
  --rules anonymize.toml \
  --profile pii-safe \
  --entity-field account.id \
  --salt rotate-2025-11 \
  --report reports/anonymize.json \
  --doctor-target app/models.py \
  ./data/users.json ./sanitized/users.json
```

- `--rules` points to a TOML/YAML/JSON file describing field patterns and strategies (faker/hash/mask). Rules are evaluated in order, can be marked `required`, and inherit presets when you pass `--profile`.
- Supply the destination as a positional argument (shown above) or via `--out/--output` if you prefer an explicit flag; directory inputs mirror their structure under the output directory. Because `pfg` proxies commands through the root Typer app, place options before the positional arguments to keep Click happy.
- Determinism helpers: `--salt` controls the hash/key derivation, `--entity-field` picks a dotted column used to derive stable pseudonyms, and `--profile` layers in the same privacy bundles available to generation commands.
- Observability: `--report` writes a JSON summary containing before/after diff samples, per-strategy counts, and privacy budget metrics. Add `--doctor-target` to reuse `pfg doctor` gap detection after data is anonymized.
- Budgets: `--max-required-misses` and `--max-rule-failures` override the thresholds defined in the rules file/profile so CI can fail fast when sensitive fields slip through unchanged.
- Input/output flexibility: accept JSON arrays, standalone objects, JSONL/NDJSON streams, or directory trees (mirrored to the output directory). Every writer preserves determinism, so running the command twice with the same salt/entity key yields identical sanitized payloads.

## `pfg fastapi`

Install the `fastapi` extra to enable FastAPI tooling.

### `pfg fastapi smoke`

```bash
pfg fastapi smoke app.main:app \
  --out tests/test_fastapi_smoke.py \
  --seed 11 \
  --dependency-override auth.get_current_user=fakes.allow_all \
  --respect-validators
```

- Generates a pytest module with one smoke test per route. Each test issues a client request, asserts a 2xx response, and validates the response model using the same deterministic fixture engine.
- `--dependency-override original=stub` (repeatable) bypasses expensive dependencies—perfect for auth/session providers or rate-limiters.
- Honour the usual deterministic flags (`--seed`, `--preset`, `--profile`, `--link`, `--with-related`, `--max-depth`, `--on-cycle`, `--rng-mode`) so smoke payloads stay in sync with the rest of your suite.

### `pfg fastapi serve`

```bash
pfg fastapi serve app.main:app \
  --port 8050 \
  --seed 7 \
  --host 0.0.0.0 \
  --reload
```

- Spins up a deterministic mock server that mirrors your FastAPI routes but responds with fixture-generated payloads. Ideal for contract-first development, front-end demos, or QA sandboxes.
- Respects the same deterministic config as every other command, and supports Uvicorn flags like `--host`, `--port`, and `--reload`.
- Combine with `--dependency-override` to stub external services when mocking.

## `pfg lock`

```bash
pfg lock \
  --lockfile .pfg-lock.json \
  --include app.User \
  ./models.py
```

- Generates a deterministic coverage manifest (defaults to `.pfg-lock.json`) that records discovery options, coverage ratios, provider assignments, and gap summaries pulled from `pfg doctor`.
- Re-run `pfg lock` after intentional model changes; use `--force` to overwrite even when nothing changed. Supports the same discovery flags as `pfg doctor` (`--schema`, `--openapi`, `--route`, etc.).
- Because `pfg` proxies commands through the root Typer app, place options before the positional module argument as shown above.

## `pfg verify`

```bash
pfg verify --lockfile .pfg-lock.json ./models.py
```

- Recomputes the manifest with the current codebase and compares it to the stored lockfile (ignoring timestamps). Exit code `30` indicates drift and prints a unified diff of the JSON payload.
- Pair `pfg lock` with `pfg verify` in CI or pre-commit hooks to block merges when coverage regresses or new models land without regenerated fixtures.
- Pass options before the positional module argument to keep the root proxy satisfied.

## `pfg snapshot`

| Subcommand | Purpose |
| ---------- | ------- |
| `pfg snapshot verify` | Regenerate artifacts in-memory and fail with exit code `30` when drift is detected (without updating files). |
| `pfg snapshot write`  | Regenerate artifacts and refresh on-disk snapshots using the same deterministic pipeline. |

```bash
pfg snapshot verify ./models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42 \
  --freeze-seeds

pfg snapshot write ./models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42
```

- Mirrors `pfg diff` options (`--json-out`, `--fixtures-out`, `--schema-out`, `--include`, `--exclude`, `--seed`, `--preset`, `--link`, `--with-related`, `--respect-validators`, `--max-depth`, `--on-cycle`, `--rng-mode`).
- Designed for CI/lint workflows where you want “diff-only” vs “update in place” behaviour without invoking the pytest plugin.
- Pair with the pytest helper documented in [testing.md](testing.md) to give individual tests opt-in updates (`pytest --pfg-update-snapshots=update`) while CI stick to `pfg snapshot verify`.

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
- Determinism helpers: `--seed`, `--freeze-seeds`, plus `--profile` to mirror the privacy bundle used in generation.
- Relations: `--link source.field=target.field` applies the same linking policy that produced the artifacts so regenerated instances stay in sync.
- Validator parity: `--respect-validators`/`--validator-max-retries` ensure diff regeneration matches the validator policy used when the golden artifacts were created.

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

## Editor integrations

- Workspace tasks and problem matchers for Visual Studio Code live under `.vscode/`.
- See [docs/vscode.md](./vscode.md) for details on running `pfg` commands directly from the editor with diagnostics surfaced in the Problems panel.

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
