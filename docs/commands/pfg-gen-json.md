# `pfg gen json`

## Capabilities

`pfg gen json` is the workhorse generator that writes JSON or JSONL payloads for one or more models. It shares the deterministic planner used by every other emitter, so the data aligns with fixtures, datasets, and schema generation. Output destinations can be templated paths (for example `{model}/{case_index}.json`) and the command emits constraint summaries plus the resolved configuration snapshot so you can trace why a run differed.

## Typical use cases

- Emit golden JSON payloads for API snapshots or SDK fixtures.
- Produce newline-delimited streams for ingestion pipelines or load tests.
- Validate a privacy profile/preset before applying it to other emitters.
- Prototype TypeAdapter expressions (`--type`) without touching the module filesystem.

## Inputs & outputs

- **Input target**: either a Python module containing models (`./models.py`), a JSON Schema via `--schema`, or a pure type expression supplied with `--type`. You must choose exactly one approach.
- **Output**: templated file(s) resolved by `--out`. When the template includes directories, fixturegen will create them atomically; multi-model templates must include `{model}` when `include` selects more than one class.
- **Result metadata**: CLI logs include `paths`, `base_output`, `config`, and optional `constraint_summary`. With `--json-errors` you’ll receive structured diagnostics instead of plain text when failures occur.

## Flag reference

**Core emission**

- `--out/-o PATH`: required. Supports template tokens `{model}`, `{case_index}`, `{timestamp}`, `{seed}`, etc.
- `--n/-n`: number of records (default 1). Combine with `--shard-size` to break large batches across files.
- `--jsonl`: switch to newline-delimited JSON. Works with sharding.
- `--indent`: override pretty-print spacing (defaults to config). Use `0` for a single line array when not using `--jsonl`.
- `--orjson/--no-orjson`: toggle the high-performance serializer without editing config.

**Discovery + selection**

- `--include/-i`, `--exclude/-e`: glob patterns targeting fully-qualified names.
- `--schema PATH`: ingest a JSON Schema file instead of importing a module. Mutually exclusive with `--type`.
- `--type "expr"`: evaluate a Python type expression via `TypeAdapter`. When present you cannot use `--link`, `--with-related`, or `--freeze-seeds` (mirrors runtime constraints). Watch mode also requires a module target so imports can refresh.

**Determinism + privacy**

- `--seed`: override the global seed for this run.
- `--now`: set a deterministic “current time” anchor (ISO timestamp) to freeze `datetime.now()` values.
- `--freeze-seeds/--no-freeze-seeds` and `--freeze-seeds-file`: persist per-model seeds (`.pfg-seeds.json` by default).
- `--preset`: apply curated strategies like `boundary` or `boundary-max`.
- `--profile`: apply privacy bundles (`pii-safe`, `realistic`, etc.).
- `--field-hints`: choose how `Field(default=...)` / `Field(examples=...)` values influence output (`defaults`, `examples`, `defaults-then-examples`, `examples-then-defaults`, `none`).
- `--locale`: override the default Faker locale for the run (e.g., `sv_SE`, `ja_JP`).
- `--locale-map pattern=locale`: repeatable option that remaps matching models/fields to specific locales without touching config files.
- `--respect-validators` + `--validator-max-retries`: repeatedly attempt generation until model/dataclass validators pass.
- `--rng-mode`: choose between `portable` (default) and `legacy` RNGs to match historical artifacts.

**Collection controls**

- `--collection-min-items` / `--collection-max-items`: clamp how many elements list/set/tuple/mapping fields emit before schema constraints run. Keep spans small for review-heavy snapshots or widen them when you need bulkier samples.
- `--collection-distribution`: bias collection lengths toward `uniform`, `min-heavy`, or `max-heavy` sections of the configured span so you can stress empty-ish or near-capacity collections on demand.

**Relations + recursion**

- `--link source.field=target.field`: declare relation join keys so regenerated payloads match existing IDs.
- `--with-related ModelA,ModelB`: emit related models alongside the primary selection (each JSON sample becomes a dict keyed by model name). Only valid when discovering from modules.
- `--max-depth`: override recursion depth budget.
- `--on-cycle`: set cycle handling policy (`reuse`, `stub`, `null`).

**Overrides + watch mode**

- `-O/--override Model.field='{...}'`: inline Use/Ignore/Require/PostGenerated overrides identical to `[tool.pydantic_fixturegen.overrides]`.
- `--watch`: watch the module, config, and output directories; rerun generation after file changes. `--watch-debounce` tunes the delay (default 0.5s).

## Example workflows

### JSONL sharded export with privacy preset

```bash
pfg gen json ./app/models.py \
  --out artifacts/{model}/run-{timestamp}.jsonl \
  --n 50000 --jsonl --shard-size 5000 \
  --include app.schemas.User \
  --profile pii-safe --preset boundary --seed 42
```

Creates 10 deterministic shards of scrubbed `User` payloads.

**Sample output**
```text
[config_loaded] include=['app.schemas.User'] exclude=[]
[json_emitted] path=/repo/artifacts/User/run-2024-06-01T12-00-00Z-000.jsonl records=5000
[json_emitted] path=/repo/artifacts/User/run-2024-06-01T12-00-00Z-001.jsonl records=5000
...
[json_emitted] path=/repo/artifacts/User/run-2024-06-01T12-00-00Z-009.jsonl records=5000
constraint_summary:
  app.schemas.User.email: faker.email -> profile=pii-safe
  app.schemas.User.id: uuid4 -> preset=boundary
```

### TypeAdapter exploration for ad-hoc expressions

```bash
pfg gen json --type "list[EmailStr]" --out /tmp/emails.json --n 5 --indent 0
```

Runs without a module, generating a single JSON array of valid `EmailStr` values at indent 0.

**Sample output**
```json
["javier@example.org","geeta@demo.io","arianna@fixtures.dev","eli@sample.net","vera@edge.test"]
```

### Bundle related models per sample

```bash
pfg gen json ./app/models.py \
  --out artifacts/bundles/{case_index}.json \
  --include app.models.Order \
  --with-related app.models.User,app.models.Address \
  --n 3 --indent 2
```

Emits three JSON objects where each record contains deterministic data for the order plus its related user and address models.

**Excerpt (`artifacts/bundles/000.json`)**
```json
{
  "Order": {
    "id": "62da5b1e-1edc-428f-87cb-1b6f93d2d0e1",
    "total_cents": 1999,
    "user_id": "6ad0ab66-6c07-42c0-9e86-5b9292e70ac4"
  },
  "User": {
    "id": "6ad0ab66-6c07-42c0-9e86-5b9292e70ac4",
    "email": "avery@example.org"
  },
  "Address": {
    "street": "826 Boundary Loop",
    "city": "Deterministic"
  }
}
```

### Additional examples

```bash
# Dataclass + TypedDict module with dense collections
pfg gen json examples/models.py \
  --include examples.Order \
  --out artifacts/{model}/dense-{case_index}.json \
  --n 10 --jsonl \
  --collection-min-items 2 --collection-max-items 5 --collection-distribution max-heavy \
  --field-hints defaults-then-examples

# TypeAdapter mode with heuristics disabled
pfg gen json --type "list[tuple[int, EmailStr]]" \
  --out artifacts/email-tuples.json \
  --n 3 --indent 0 --rng-mode portable
```

Python API equivalent:

```python
from pathlib import Path
from pydantic_fixturegen.api import generate_json
from pydantic_fixturegen.core.path_template import OutputTemplate

generate_json(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("artifacts/{model}.json"),
    count=5,
    jsonl=True,
    include=["examples.Order"],
    collection_min_items=2,
    collection_max_items=4,
    field_hints="defaults",
)
```

Find more combinations (datasets, fixtures, persistence, Python APIs) in [docs/examples.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/examples.md).

## Operational notes

- When using `--schema`, fixturegen writes a transient module under `.pfg-cache` and watches the schema file when `--watch` is enabled.
- Each run logs the resolved `include`/`exclude` values, RNG mode, time anchor, and relations so diffs remain explainable.
- Exit codes follow Typer defaults: `0` success, `1` for `EmitError`/`DiscoveryError`. Structured hints contain `details` such as the missing relation field or invalid output template.
- Constraint summaries print once per run with counts of constrained fields; parse them downstream if you need coverage metrics.

## Related docs

- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-json)
- [Output path templates](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md)
- [Seeds & presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md)
- [Overrides + emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#overrides)
