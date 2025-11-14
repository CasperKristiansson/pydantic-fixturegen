# `pfg gen seed sqlmodel`

## Capabilities
`pfg gen seed sqlmodel` connects to a SQLModel/SQLAlchemy database, generates deterministic instances for the selected models, and inserts them in batches. It shares the generator used by `pfg gen json`, so relations, presets, and freeze files behave identically, but wraps the output in a transactional seeding pipeline.

## Typical use cases
- Populate a local SQLite/Postgres database with realistic data before manual testing.
- Seed integration test databases during CI with rollback mode.
- Generate reference data in staging environments while keeping seeds, presets, and privacy bundles aligned with fixture runs.

## Inputs & outputs
- **Target**: module path or `--schema` (JSON Schema). Optional if you seed from a schema-only spec.
- **Database**: `--database/-d` SQLAlchemy URL. The command refuses to connect unless the URL scheme is listed in `--allow-url` (defaults to `sqlite://` and `sqlite:///`) to prevent accidental production writes.
- **Result**: CLI logs the number of inserted rows, whether a rollback/dry-run occurred, and emits warnings when truncation or schema creation executes.

## Flag reference
**Generation plan**
- `--n/-n`: number of primary records (per run). Related records are generated automatically when `--with-related` is used.
- `--include/-i`, `--exclude/-e`: discovery filters.
- `--schema`: ingest JSON Schema instead of importing.
- Determinism flags: `--seed`, `--now`, `--freeze-seeds`, `--freeze-seeds-file`, `--preset`, `--profile`, `--rng-mode`.
- Locale overrides: `--locale` for a global Faker locale and repeatable `--locale-map pattern=locale` for per-model overrides during seeding.
- Relation/depth controls: `--link`, `--with-related`, `--max-depth`, `--on-cycle`.
- Validator controls: `--respect-validators`, `--validator-max-retries`.

**Database behavior**
- `--database/-d`: required SQLAlchemy URL (sqlite, postgres, mysql, etc.).
- `--allow-url`: repeatable whitelist of allowed URL prefixes (only applies to SQLModel command). Add entries like `postgresql://` when you intentionally seed a server DB.
- `--batch-size`: records generated per transaction batch (default 50). Tune for large inserts.
- `--rollback/--commit`: wrap the entire run in a transaction that rolls back at the end (default commit). Handy for smoke tests.
- `--dry-run`: skip inserts entirely but log generated payloads.
- `--truncate/--no-truncate`: delete existing rows for the selected models before seeding.
- `--auto-primary-keys/--keep-primary-keys`: default `--auto-primary-keys` nulls SQLModel primary keys whose default is `None` so the database can autoincrement them. Pass `--keep-primary-keys` if you intentionally supply your own IDs.
- `--create-schema/--no-create-schema`: call `SQLModel.metadata.create_all()` before inserts.
- `--echo/--no-echo`: toggle SQLAlchemy engine echo logging to stdout.

## Example workflows
### Seed a SQLite database with rollback disabled
```bash
pfg gen seed sqlmodel ./app/models.py \
  --database sqlite:///tmp/app.db \
  --n 100 --include app.models.User \
  --seed 7 --preset boundary --freeze-seeds \
  --batch-size 200 --truncate --create-schema
```
Creates tables (if missing), truncates existing rows, and inserts 100 deterministic `User` records.

**Sample output**
```text
[sqlmodel_connect] url=sqlite:///tmp/app.db create_schema=True truncate=True
[seed_plan] include=['app.models.User'] relations=0 preset=boundary freeze_file=.pfg-seeds.json
Inserted 100 rows across 1 model(s) (rollback=False dry_run=False)
```

**Row preview (`sqlite3 tmp/app.db 'SELECT id,email FROM user LIMIT 2;'`)**
```text
6ad0ab66-6c07-42c0-9e86-5b9292e70ac4|avery@example.org
9c7e0cf1-9f0f-49ed-9e5c-1c0c46e5b9ab|rivera@example.org
```

### Safety-first smoke test with rollback
```bash
pfg gen seed sqlmodel ./app/models.py \
  --database sqlite:///tmp/test.db --rollback --dry-run --n 5
```
Generates rows but never commits changes, making it safe for CI verification.

**Sample output**
```text
[sqlmodel_connect] url=sqlite:///tmp/test.db rollback=True dry_run=True
Generated batch size=5 (dry run, nothing inserted)
```

### Large batch with auto-incrementing primary keys
```bash
pfg gen seed sqlmodel ./examples/sql_models.py \
  --database sqlite:///tmp/sql_seed.db \
  --include examples.sql_models.Customer \
  --n 200 --truncate --create-schema --batch-size 100
```
Seeds 200 deterministic `Customer` rows, truncating the table first and letting SQLite autoincrement the primary key columns (`--auto-primary-keys` is enabled by default).

**Sample output**
```text
[sqlmodel_connect] url=sqlite:///tmp/sql_seed.db create_schema=True truncate=True auto_primary_keys=True
Inserted 200 rows across 1 model(s) (rollback=False dry_run=False)
```

**Row preview (`sqlite3 tmp/sql_seed.db 'SELECT id,email FROM customer LIMIT 2;'`)**
```text
1|mirror.theodore@example.com
2|rocio.lee@example.org
```


## Operational notes
- The command builds a `ModelArtifactPlan` once and reuses it for every batch, so large seed runs stay consistent even when `--with-related` fans out.
- On failure fixturegen closes the SQLAlchemy engine via `dispose()` to avoid leaking connections.
- JSON Schema ingestion uses the same cache as other schema-aware commands, so repeated runs do not thrash the filesystem.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-seed)
- [ORM integrations](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md#database-seeding)
- [Seeds & presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md)
