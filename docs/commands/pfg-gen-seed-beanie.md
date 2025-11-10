# `pfg gen seed beanie`

## Capabilities
`pfg gen seed beanie` generates deterministic documents and inserts them into a MongoDB database using Beanie. It mirrors every planning option from the SQLModel variant but swaps in Beanie-specific behaviors such as cleanup mode and Mongo-safe URL allow-lists.

## Typical use cases
- Seed a local MongoDB/Atlas instance with fixture data before manual testing.
- Populate QA clusters using deterministic seeds so smoke tests stay reproducible.
- Run cleanup mode to insert documents for validation and then delete them automatically.

## Inputs & outputs
- **Target**: module path or `--schema` for JSON Schema ingestion.
- **Database**: Mongo-style URI (for example `mongodb://localhost:27017/app`). Fixturegen refuses to connect unless the scheme matches `--allow-url` (defaults `mongodb://`, `mongomock://`).
- **Result**: logs the number of documents inserted, whether cleanup took place, and whether the run was dry.

## Flag reference
**Shared planning options**
- `--n/-n`, `--include`, `--exclude`, `--seed`, `--now`, `--preset`, `--profile`, `--freeze-seeds`, `--freeze-seeds-file`, `--link`, `--with-related`, `--max-depth`, `--on-cycle`, `--rng-mode`, `--respect-validators`, `--validator-max-retries`, `--schema` — identical to the SQLModel command.

**Beanie-specific controls**
- `--database/-d`: Mongo connection string (can include credentials and query parameters).
- `--allow-url`: repeatable whitelist of allowed URI prefixes. Extend this when targeting Atlas or SRV URIs.
- `--batch-size`: number of documents per insertion chunk (default 50).
- `--cleanup/--keep`: when enabled, wraps each insert in a matching delete so the database returns to its prior state after validation. Useful for doctor-style audits.
- `--dry-run`: log generated payloads without talking to MongoDB.

## Example workflows
### Seed a local MongoDB instance
```bash
pfg gen seed beanie ./app/models.py \
  --database mongodb://localhost:27017/app \
  --n 250 --include app.models.Order \
  --seed 42 --preset realistic --with-related app.models.User
```
Inserts 250 `Order` documents (each with a related `User`) into the `app` database.

**Sample output**
```text
[beanie_connect] url=mongodb://localhost:27017/app cleanup=False dry_run=False
Inserted documents: app.models.Order=250, related={'app.models.User':250}
```

**Mongo preview (`db.order.findOne({}, {_id:0})`)**
```json
{
  "id": "be0773e6-ecbb-46e5-93d7-8db3cb8e9c8a",
  "total_cents": 4599,
  "user_id": "6ad0ab66-6c07-42c0-9e86-5b9292e70ac4",
  "status": "PENDING"
}
```

### Cleanup mode for integration verification
```bash
pfg gen seed beanie ./app/models.py \
  --database mongodb://localhost:27017/app \
  --n 10 --cleanup --dry-run
```
Generates documents, logs them, and skips writes because of `--dry-run`. Drop `--dry-run` to perform insert/delete cycles automatically.

**Sample output**
```text
[beanie_connect] url=mongodb://localhost:27017/app cleanup=True dry_run=True
Cleanup enabled; generated payloads discarded (0 writes executed)
```

## Operational notes
- Fixturegen extracts the database name from the Mongo URI so Beanie can target the correct database even when SRV URIs are used.
- Cleanup mode is invaluable when you want to observe generated payloads via MongoDB triggers without mutating long-lived data sets.
- The CLI suppresses deprecated `model_fields` warnings emitted by Beanie with Pydantic v2 so logs stay clean.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-seed)
- [ORM integrations](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md#database-seeding)
- [Providers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md)
