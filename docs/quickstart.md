# Quick start: Build deterministic Pydantic fixtures fast

> Follow one file from discovery to fixtures, learn config precedence, and watch artifacts regenerate on change.

## You need

- Python 3.10–3.14.
- `pip install pydantic-fixturegen` (add extras like `orjson`, `regex`, `hypothesis`, `openapi`, `fastapi`, or `watch` as needed).
- A small Pydantic v2 model module.

## Step 1 — Create a model file

```python
# models.py
from pydantic import BaseModel

class Address(BaseModel):
    street: str

class User(BaseModel):
    id: int
    name: str
    nickname: str | None = None
    address: Address
```

You can drop this file alongside your test suite or inside a sample project root.

## Step 2 — Discover models

```bash
pfg list ./models.py
```

You see fully-qualified names such as:

```text
models.User
models.Address
```

Use `--include`/`--exclude` to target specific classes, `--public-only` to respect `__all__`, or `--ast` when imports are unsafe.
Machine-readable errors are available with `--json-errors`; discovery failures surface error code `20`.

## Step 3 — Generate JSON artifacts

```bash
pfg gen json ./models.py --include models.User --n 2 --indent 2 --out ./out/User
```

- `--include` narrows generation when the module exposes many models.
- `--out` accepts template placeholders like `{model}`, `{case_index}`, and `{timestamp}`.
- `--indent` adds a metadata banner containing `seed`, `version`, and `digest`.
- Add `--jsonl` and `--shard-size` when you stream large datasets.

The command writes `out/User.json` with deterministic content:

```json
/* seed=42 version=1.0.0 digest=<sha256> */
[
  {
    "id": 1,
    "name": "Alice",
    "nickname": null,
    "address": { "street": "42 Main St" }
  },
  {
    "id": 2,
    "name": "Bob",
    "nickname": "b",
    "address": { "street": "1 Side Rd" }
  }
]
```

## Step 3b — Generate tabular datasets

When you need warehouse-friendly sinks instead of JSON blobs, install the `dataset` extra (`pip install 'pydantic-fixturegen[dataset]'`) and stream directly to CSV, Parquet, or Arrow:

```bash
pfg gen dataset ./models.py \
  --include models.User \
  --format parquet \
  --compression zstd \
  --n 500000 \
  --shard-size 100000 \
  --out ./warehouse/users.parquet
```

- CSV writers stream line-by-line (add `--compression gzip` if you want `.csv.gz` files), and the PyArrow-backed Parquet/Arrow emitters flush in batches so multi-million record runs stay memory-friendly.
- The column order derives from your Pydantic model and includes a `__cycles__` column whenever recursion policies fire, making QA investigations trivial.
- Seeds, presets, validator retries, relation links, and cycle policies mirror the `gen json` options, so you can share a single configuration block across emitters.

## Step 4 — Seed integration databases

Install the `[seed]` extra and populate an actual database when running integration tests:

```bash
pfg gen seed sqlmodel ./models.py \
  --database sqlite:///seed.db \
  --include models.User \
  --n 25 \
  --create-schema \
  --batch-size 10 \
  --truncate
```

- The SQLModel seeder wraps inserts in a transaction; add `--rollback` when you want to keep the database pristine between tests or `--truncate` when you want a clean slate before writing.
- For MongoDB-backed stacks, swap `sqlmodel` for `beanie` and point `--database` at `mongodb://...`; adding `--cleanup` deletes inserted documents at the end.
- Deterministic flags (`--seed`, `--profile`, `--link`, `--with-related`, etc.) behave exactly like JSON/dataset emitters, so your fixtures and databases stay in sync.

## Step 5 — Emit pytest fixtures

### No models yet? Start from schema or OpenAPI

Install the `openapi` extra (`pip install 'pydantic-fixturegen[openapi]'`) and let the CLI scaffold temporary models under the hood:

```bash
# Standalone JSON Schema
pfg gen json --schema contracts/user.schema.json --out out/{model}.json

# OpenAPI components per route
pfg gen openapi api.yaml --route "GET /users" --route "POST /orders" --out openapi/{model}.json
```

- `--schema` feeds the document through `datamodel-code-generator`, caches the generated module under `.pfg-cache/schemas`, and immediately reuses it for `gen json`, `diff`, or `doctor` runs.
- `pfg gen openapi` isolates the schemas referenced by the selected HTTP methods and writes one artifact per component—use `{model}` in your template to isolate each response/request body.
- `pfg doctor --schema ...` / `--openapi ...` surface coverage gaps without writing Python models first.

Schema-derived modules are cached and invalidated automatically when the underlying document (or selected routes) change.

### FastAPI smoke + mock server

Install the `fastapi` extra to unlock the new commands:

```bash
pip install 'pydantic-fixturegen[fastapi]'

pfg fastapi smoke app.main:app --out tests/test_fastapi_smoke.py
pfg fastapi serve app.main:app --port 8050 --seed 7
```

- The smoke command generates a pytest module (one test per route) using fixture data, asserts responses stay 2xx, and validates response models. Pass `--dependency-override original=stub` to bypass auth dependencies.
- The mock server mirrors your FastAPI routes but returns deterministic JSON payloads, making it easy to share a contract-first API without deploying the real backend.

### Bridge existing Polyfactory factories

```bash
pip install 'pydantic-fixturegen[polyfactory]'

pfg gen polyfactory ./models.py --out tests/factories.py --include app.models.User
```

- With the extra installed, fixturegen automatically discovers `ModelFactory` subclasses in your project (including `app.factories`-style modules) and delegates matching models to them for `gen json`, `gen fixtures`, and FastAPI/mock workflows—no double maintenance when migrating.
- Set `[polyfactory] prefer_delegation = false` if you only want detection logs; you can still export wrapper factories via `pfg gen polyfactory` so teams that rely on Polyfactory APIs can call your new fixturegen-powered implementations.
- The generated module includes `seed_factories(seed)` so test suites can reseed the shared `InstanceGenerator`, and every exported factory still honors keyword overrides by falling back to Polyfactory’s native `build()` implementation when explicit kwargs are provided.

### OpenAPI examples via fixtures

```bash
pfg gen examples openapi.yaml --out openapi.examples.yaml
```

- The command uses the same schema-ingestion pipeline to attach realistic `example` blocks to every referenced schema or component, so docs and SDKs inherit the exact payloads your fixtures produce.

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_user_fixtures.py \
  --style functions --scope module --cases 3 --return-type model
```

You receive a formatted module with deduplicated imports and a banner:

```python
# pydantic-fixturegen v1.0.0  seed=42  digest=<sha256>
import pytest
from models import User, Address

@pytest.fixture(scope="module", params=[0, 1, 2], ids=lambda i: f"user_case_{i}")
def user(request) -> User:
    ...
```

Tune `--style` (`functions`, `factory`, `class`), `--scope` (`function`, `module`, `session`), and `--return-type` (`model`, `dict`) to match your test style.
Add `--p-none` to bias optional fields.

## Step 6 — Export JSON Schema

```bash
pfg gen schema ./models.py --out ./schema
```

Schema files write atomically to avoid partial artifacts.
Combine with `--watch` to rebuild on file changes.

## Step 7 — Explain generation strategies

```bash
pfg gen explain ./models.py --tree
```

You see an ASCII tree per field. Switch to machine-readable output with `--json`, cap recursion with `--max-depth`, and limit models with `--include` or `--exclude`.

```text
User
 ├─ id: int ← number_provider(int)
 ├─ name: str ← string_provider
 ├─ nickname: Optional[str] ← union(p_none=0.25)
 └─ address: Address ← nested model
```

Use this view to confirm plugin overrides or preset tweaks.

## Step 8 — Property-based tests with Hypothesis

Install the `hypothesis` extra and import `strategy_for` whenever you need shrinkable strategies:

```python
from hypothesis import given
from pydantic_fixturegen.hypothesis import strategy_for
from models import User


@given(strategy_for(User, profile="edge"))
def test_user_round_trips_through_api(instance: User) -> None:
    payload = instance.model_dump()
    restored = User.model_validate(payload)
    assert restored == instance
```

Prefer repeatable fixtures? Generate a python module with `pfg gen strategies models.py --out tests/strategies.py --strategy-profile edge` and import the exported `user_strategy` in multiple tests without writing boilerplate.

## Step 9 — Deterministic anonymization

Start by declaring rule sets in TOML/YAML/JSON:

```toml
[anonymize]
salt = "rotation-nov-2025"
entity_field = "account.id"

  [[anonymize.rules]]
  pattern = "*.email"
  strategy = "faker"
  provider = "email"
  required = true

  [[anonymize.rules]]
  pattern = "*.ssn"
  strategy = "hash"
  hash_algorithm = "sha1"
  required = true

  [[anonymize.budget]]
  max_required_rule_misses = 0
  max_rule_failures = 0
```

Then run:

```bash
pfg anonymize \
  --rules anonymize.toml \
  --profile pii-safe \
  --report reports/anonymize.json \
  --doctor-target app/models.py \
  ./data/users.json ./sanitized/users.json
```

- Rule patterns are glob-friendly dotted paths (`users.*.email`, `orders[*].card.last4`) and strategies include `faker`, `hash`, and `mask`.
- Determinism comes from the salt, entity key, and optional privacy profile. Change the salt to rotate pseudonyms without editing rules. When invoking via `pfg`, place options before the positional arguments so the proxy forwards them correctly.
- Privacy budgets fail the run when required rules never match or a strategy throws; the JSON report logs every replacement count, diff sample, and coverage summary from `pfg doctor` when you pass `--doctor-target`.
- Need the functionality inside Python? `from pydantic_fixturegen.api import anonymize_from_rules` returns the sanitized payload plus the same report structure.

## Step 10 — Enforce coverage with lockfiles

```bash
pfg lock --lockfile .pfg-lock.json ./models.py
pfg verify --lockfile .pfg-lock.json ./models.py
```

- The lockfile records per-model coverage, provider assignments, and gap summaries pulled from `pfg doctor`. Commit it to your repo just like other lockfiles.
- `pfg verify` recomputes coverage and fails when anything drifts; the unified diff in the failure output highlights exactly which model/field needs attention.
- Run `pfg lock` after intentional schema changes (or add it to release scripts) so pull requests only contain meaningful coverage updates.

## Watch mode

<a id="watch-mode"></a>

Install the `watch` extra, then run:

```bash
pip install 'pydantic-fixturegen[watch]'
pfg gen json ./models.py --out ./out/User.json --watch
```

- The CLI monitors Python and configuration files beneath the working directory.
- `--watch-debounce <seconds>` controls the filesystem event throttle (default `0.5`).
- Combine with `--freeze-seeds` to keep deterministic outputs even as models change.

Watch mode is available on `gen json`, `gen fixtures`, and `gen schema`.

## Configuration checkpoints

- Run `pfg init` to scaffold `[tool.pydantic_fixturegen]` with sensible defaults (seed `42`, union policy `weighted`, enum policy `random`, pytest scope `module`).
- The precedence order is `CLI > environment (PFG_*) > pyproject.toml/YAML > defaults`.
- Reference the schema directly with `pfg schema config --out schema/config.schema.json`.
- Use `.pfg-seeds.json` with `--freeze-seeds` for reproducible CI runs; see [docs/seeds.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md).

## Quick command reference

```bash
# Scaffold configuration files
pfg init --yaml

# Diff regenerated artifacts against stored outputs
pfg diff models.py --json-out out/current.json --show-diff

# Validate configuration without generating artifacts
pfg check models.py --json-errors

# Regenerate JSON automatically (requires [watch] extra)
pfg gen json models.py --out out/models.json --watch

# Export configuration schema
pfg schema config --out schema/config.schema.json
```

## Troubleshooting tips

- Discovery import errors? Switch to `--ast` or fix `PYTHONPATH`. Capture machine-readable details with `--json-errors`.
- Non-deterministic outputs? Pin `--seed` or `PFG_SEED` and inspect banner metadata.
- Large files choking CI? Use `--jsonl` and `--shard-size`, or enable `--orjson` via the `orjson` extra.
- Optional fields feel off? Adjust `--p-none` or configure `field_policies` in `pyproject.toml`.
- Sandbox blocked a write or socket? Move output beneath the working directory; network calls are intentionally disabled.

Next: explore deeper recipes in the [Cookbook](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md) or tighten config options in the [Configuration guide](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md).
