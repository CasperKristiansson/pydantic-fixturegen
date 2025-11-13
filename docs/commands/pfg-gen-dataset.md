# `pfg gen dataset`

## Capabilities
`pfg gen dataset` emits large CSV, Parquet, or Arrow datasets using the same deterministic generator that powers JSON output. It is optimized for bulk export: records stream in batches, optional compression keeps artifacts small, and sharding prevents multi-gigabyte files.

## Typical use cases
- Build reproducible datasets for analytics or lakehouse ingestion.
- Produce Parquet snapshots for DuckDB/Athena tests without touching production data.
- Export CSV slices for QA workflows that must mirror fixture seeds.
- Validate cross-model relations under realistic volume before seeding a database.

## Inputs & outputs
- **Target**: module path exposing Pydantic models, stdlib `@dataclass` types, or `TypedDict`s (or use `--schema` for JSON Schema). Required unless a schema is provided.
- **Format**: `--format csv|parquet|arrow` (default `csv`). Columnar formats require the `dataset` extra so PyArrow is available.
- **Output**: `--out` accepts file templates; include `{model}` whenever more than one model is selected.
- **Compression**: `--compression` chooses codecs. CSV supports `gzip`; Parquet/Arrow support `snappy`, `zstd`, `brotli`, `lz4` (Arrow also `zstd`/`lz4`). Leave unset for uncompressed output.

## Flag reference
**Volume + layout**
- `--n/-n`: number of records (default 1).
- `--shard-size`: max records per file. Helps when `--n` is huge.
- `--format`, `--compression` as described above.

**Discovery & schema ingestion**
- `--include/-i`, `--exclude/-e`: glob filters.
- `--schema PATH`: ingest JSON Schema instead of importing a module.

**Determinism + privacy**
- `--seed`, `--now`, `--preset`, `--profile`, `--rng-mode`: same semantics as `pfg gen json`.
- `--freeze-seeds`, `--freeze-seeds-file`: persist per-model seeds between runs.
- `--field-hints`: prefer `Field` defaults/examples before providers (modes match `pfg gen json`).
- `--locale` / `--locale-map pattern=locale`: override the Faker locale globally or remap specific models/fields for international datasets without editing `pyproject.toml`.

**Collection controls**
- `--collection-min-items` / `--collection-max-items`: clamp global collection lengths before field-level constraints. Handy when you need denser arrays or when CSV tests only expect a couple of elements per list.
- `--collection-distribution`: skew sampling toward smaller (`min-heavy`) or larger (`max-heavy`) collections, or keep it `uniform`.

**Quality controls**
- `--respect-validators`, `--validator-max-retries`: enforce Pydantic validators before rows hit disk.
- `--link`, `--max-depth`, `--on-cycle`: keep relations and recursion behavior aligned with other emitters.
- `-O/--override`: per-field overrides using the same JSON snippet semantics as config files.

**Watch mode**
- `--watch`: monitor the module, schema (if provided), config, and output directory. `--watch-debounce` throttles reruns.

## Example workflows
### Parquet warehouse export
```bash
pfg gen dataset ./app/models.py \
  --out warehouse/{model}/{timestamp}.parquet \
  --format parquet --compression zstd \
  --n 1_000_000 --shard-size 250_000 \
  --include app.schemas.Order --seed 7 \
  --preset boundary-max --profile realistic
```
Produces four Zstandard-compressed Parquet shards with deterministic `Order` rows.

**Sample output**
```text
[dataset_emit] format=parquet compression=zstd shard=250000
warehouse/app.schemas.Order/2024-06-01T12-00-00Z-000.parquet (250000 rows)
warehouse/app.schemas.Order/2024-06-01T12-00-00Z-001.parquet (250000 rows)
warehouse/app.schemas.Order/2024-06-01T12-00-00Z-002.parquet (250000 rows)
warehouse/app.schemas.Order/2024-06-01T12-00-00Z-003.parquet (250000 rows)
constraint_summary:
  total_fields=42 constrained=9 warnings=0
```
**Parquet preview via `pyarrow.parquet.read_table(...).to_pandas().head(2)`**
```text
order_id                           total_cents   status   user_id
0  3fa85f64-5717-4562-b3fc-2c963f66afa6  1999          PENDING  1b111c11-...
1  8d6548ba-52a5-41b4-80f3-4f28c1c9dcef  4599          CAPTURED 2a222d22-...
```

### Schema-driven CSV for integration tests
```bash
pfg gen dataset --schema spec/schema.json \
  --out artifacts/{model}.csv --format csv --compression gzip \
  --n 1000 --respect-validators --preset edge
```
Ingests a JSON Schema file instead of importing the module and writes gzipped CSV files per schema.

**Sample output**
```text
[schema_ingest] spec=spec/schema.json cached_path=.pfg-cache/schema/spec_schema_models.py
[csv_emit] path=artifacts/Event.csv.gz rows=1000 compression=gzip
[csv_emit] path=artifacts/Address.csv.gz rows=1000 compression=gzip
Inserted warnings: 0 validator_retries: 3
```
**Excerpt from `artifacts/Event.csv.gz` (after `gunzip`)**
```csv
id,timestamp,event_type,metadata
3014d4e8-75de-4b9a-8a5d-a3d4ab610e1a,2025-11-08T12:00:00Z,USER_SIGNED_IN,"{'ip':'203.0.113.42'}"
fe71b998-6af3-4f68-90a2-615efa170f29,2025-11-08T12:00:00Z,PASSWORD_RESET,"{'ip':'203.0.113.87'}"
```

### Additional examples

```bash
# Parquet export from a module that mixes BaseModel, dataclass, and TypedDict types
pfg gen dataset examples/models.py \
  --include examples.Order \
  --format parquet --compression zstd \
  --n 25000 --shard-size 5000 \
  --out warehouse/{model}/{timestamp}.parquet \
  --collection-min-items 1 --collection-max-items 3

# CSV + gzip plus field hints for defaults/examples
pfg gen dataset examples/models.py \
  --format csv --compression gzip \
  --n 1000 --out artifacts/{model}.csv.gz \
  --field-hints defaults-then-examples
```

Python API equivalent:

```python
from pathlib import Path
from pydantic_fixturegen.api import generate_dataset
from pydantic_fixturegen.core.path_template import OutputTemplate

generate_dataset(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("warehouse/{model}-{case_index}.parquet"),
    count=5000,
    format="parquet",
    compression="zstd",
    include=["examples.Order"],
    collection_distribution="max-heavy",
)
```

More ready-to-run shells + notebooks live in [docs/examples.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/examples.md#cli-flows).

## Operational notes
- Each run logs constraint summaries plus the resolved dataset format. For Parquet/Arrow the logger also captures the PyArrow version (when verbose logging is enabled) to aid reproducibility.
- When multiple schemas are selected and the output template omits `{model}`, the command exits early with a `DiscoveryError` so you never accidentally clobber files.
- CI tip: combine `--watch` with `entr`/`watchexec` locally, but disable it in automation because the process will stay alive.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-dataset)
- [Dataset emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md#dataset-emitter)
- [Output templates](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md)
- [Seeds & presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md)
