# Quickstart: deterministic data in minutes

> Install the CLI, generate JSON/datasets/fixtures, diff them, and lock in deterministic snapshots.

## 0. Before you begin

```bash
python -m pip install --upgrade pip
pip install "pydantic-fixturegen[openapi,fastapi,dataset,polyfactory]"
pfg --version
```

- Add extras that match your stack (`openapi` for schema ingestion, `fastapi` for smoke/mock commands, `dataset` for CSV/Parquet/Arrow, `polyfactory` if you already have ModelFactory classes, `seed` for SQLModel + Beanie).
- Run `pfg --help` once to ensure the entry point is on your PATH. All CLI examples assume a POSIX shell; on Windows, swap `\` for ``^`` when you wrap long commands.

## 1. Scaffold a model module

Create `models.py` anywhere inside your repo:

```python
from pydantic import BaseModel, Field


class Address(BaseModel):
    street: str
    city: str


class User(BaseModel):
    id: int
    name: str
    nickname: str | None = None
    address: Address
    email: str = Field(regex=r".+@example.org$")
```

Inspect it with `pfg list models.py --include models.User` to confirm discovery works. Need a config file? `pfg init --seed 42 --json-indent 2` writes TOML/YAML templates so you can persist defaults (seed, presets, emitters).

## 2. Generate JSON and datasets

### JSON / JSONL / sharded payloads

```bash
pfg gen json ./models.py \
  --include models.User \
  --out artifacts/{model}/sample-{case_index}.json \
  --n 5 \
  --indent 2 \
  --seed 42 \
  --freeze-seeds \
  --preset boundary \
  --watch
```

- `--include` narrows generation when the module exports multiple models.
- `--out` accepts placeholders (`{model}`, `{case_index}`, `{timestamp}`) so you can route artifacts per model/shard.
- Use `--jsonl` for newline-delimited output or `--shard-size` to split runs without buffering everything in memory.
- `--seed` and `--freeze-seeds` keep runs deterministic even after adding/removing models; the header banner records `seed`, `version`, and `model-digest`.
- `--preset boundary` applies opinionated constraints (higher optional `None` frequency, min/max numeric bias). Add `--respect-validators` if your models enforce `@field_validator` rules.

### CSV / Parquet / Arrow datasets

```bash
pfg gen dataset ./models.py \
  --include models.User \
  --format parquet \
  --compression zstd \
  --n 100000 \
  --shard-size 25000 \
  --out warehouse/users.parquet
```

- Install the `dataset` extra to pull in PyArrow.
- `--format csv|parquet|arrow` controls the sink; CSVs stream row-by-row (add `--compression gzip` for `.csv.gz`), while columnar formats flush in batches.
- Shards/multiple files use the same templating rules as JSON emission, and every dataset includes a `__cycles__` column if recursion policies (max depth, cycle policy) fire.

## 3. Emit pytest fixtures or seeds

```bash
pfg gen fixtures ./models.py \
  --include models.User \
  --out tests/fixtures/test_users.py \
  --style functions \
  --scope module \
  --cases 3 \
  --return-type model
```

- Swap `--style factory` or `--style class` to match the test style you prefer.
- `--return-type dict` keeps fixtures JSON-serialisable.
- The generated module includes a banner with seed + digest so diffs are easy to audit.

Need a populated database for integration tests?

```bash
pfg gen seed sqlmodel ./models.py \
  --database sqlite:///seed.db \
  --include models.User \
  --n 25 \
  --create-schema \
  --truncate \
  --rollback
```

For MongoDB stacks, replace `sqlmodel` with `beanie` and install the `seed` extra. Both commands honour the same determinism knobs (`--seed`, `--preset`, `--link`, `--with-related`, `--respect-validators`, `--max-depth`, `--on-cycle`, `--rng-mode`).

## 4. Diff & snapshot artifacts

```bash
pfg diff ./models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --schema-out schema \
  --show-diff \
  --seed 42 \
  --freeze-seeds
```

Diff reruns generation in-memory and compares against existing files. Combine with `pfg check` to validate configs without writing new files.

Lock in deterministic reviews with snapshots:

```bash
pfg snapshot verify ./models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42

pfg snapshot write ./models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42
```

Pair snapshot commands with the [pytest plugin](testing.md) to let `pfg_snapshot` assertions update on demand (`pytest --pfg-update-snapshots=update`) while CI runs `pfg snapshot verify` to block regressions.

Finally, capture a coverage manifest and enforce it in CI:

```bash
pfg lock ./models.py --lockfile .pfg-lock.json
pfg verify ./models.py --lockfile .pfg-lock.json
```

## 5. Layer on advanced workflows

### Watch & explain

- Add `--watch --watch-debounce 0.5` to any generation command for live regeneration.
- Use `pfg gen explain ./models.py --tree --include models.User` to visualise heuristic/provider choices when debugging deterministic output.

### Schema ingestion & OpenAPI examples

```bash
pfg gen json --schema contracts/user.schema.json --out artifacts/{model}.json
pfg gen openapi api.yaml --route "GET /users" --out openapi/{model}.json
pfg gen examples api.yaml --out api.examples.yaml
```

The `openapi` extra pulls in `datamodel-code-generator` and PyYAML so schema ingestion, OpenAPI fan-out, and example injection require no manual scaffolding.

### FastAPI smoke tests & mock servers

```bash
pfg fastapi smoke app.main:app --out tests/test_fastapi_smoke.py
pfg fastapi serve app.main:app --port 8050 --seed 7
```

Dependency overrides (`--dependency-override original=stub`) let you bypass auth/session providers, and both commands reuse your deterministic settings so contract drift shows up as diff noise immediately.

### Polyfactory interoperability

```bash
# auto-detect ModelFactory subclasses when the polyfactory extra is installed
pfg gen json ./models.py --include models.User --seed 15

# export wrapper factories that call fixturegen under the hood
pfg gen polyfactory ./models.py --out tests/factories_pfg.py --seed 15
```

Set `[polyfactory] prefer_delegation = true` in your config to let fixturegen defer to existing factories while still controlling seeds, presets, and relation wiring.

### Datasets + anonymizer + FastAPI?

See [Emitters](emitters.md) for CSV/Parquet/Arrow details, [anonymize](emitters.md#anonymizer) for rule syntax, and [features](features.md) for FastAPI, Hypothesis, and seeding highlights.

## Next steps

- Adopt the [Cookbook](cookbook.md) recipes for CI diffing, dataset streaming, SQL seeding, or Polyfactory migrations.
- Explore the [CLI reference](cli.md) and [API reference](api.md) when you automate these flows.
- Compare fixturegen with your current approach via [Alternatives & migration guides](alternatives.md).

Because every command shares the same deterministic engine, once you lock in seeds/presets, any new workflow (snapshots, anonymizer, FastAPI smoke tests, Polyfactory exports) becomes a copy-paste away.
