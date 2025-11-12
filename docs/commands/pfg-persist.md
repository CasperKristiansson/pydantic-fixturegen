# `pfg persist`

Persist generated Pydantic payloads through reusable handlers (HTTP, SQLite, custom plugins) instead of writing JSON/fixtures to disk. The command reuses the same discovery/generation pipeline as `pfg gen json`, so flags like `--include`, `--seed`, `--override`, and `--field-hints` behave identically before the handler sees any data.

## Typical use cases

- Seed staging databases or sandboxes by streaming generated models into SQLite/Postgres ingestion scripts.
- POST curated payloads to HTTP endpoints (Webhooks, internal APIs) without writing intermediate artifacts.
- Wire house-built persistence handlers via entry points (Kafka producers, S3 uploaders, etc.) and keep CI logic outside of test suites.

## Handler discovery

- Built-in shortcuts:
  - `http-post`: synchronous HTTP POST/PUT with JSON batches (options: `url`, `method`, `headers`, `timeout`, `envelope`).
  - `http-post-async`: async wrapper around the HTTP handler, useful inside async-aware plugins.
  - `sqlite-json`: writes payloads as JSON rows inside a SQLite table (options: `database`, `table`, `ensure_table`, `journal_mode`).
- Add named aliases via `[tool.pydantic_fixturegen.persistence.handlers.<name>]` and reference them with `--handler <name>`.
- Provide ad-hoc dotted paths (e.g. `myapp.handlers:KafkaHandler`) or entry-point plugins that implement `pfg_register_persistence_handlers`.

## Flag reference

- `--handler/-H NAME`: required. Registered handler name or dotted path (`pkg.module:callable`).
- `--handler-config JSON`: optional JSON object merged into handler keyword arguments.
- `--n/-n`: number of records (default 1).
- `--batch-size`: group size per handler invocation (default 50).
- `--max-retries`: number of retry attempts per batch (default 2).
- `--retry-wait`: seconds to wait between retry attempts (default 0.5).
- Generation flags reused from `pfg gen json`: `--include/--exclude`, `--seed`, `--preset`, `--profile`, `--field-hints`, `--link`, `--with-related`, `--override`, `--respect-validators`, `--validator-max-retries`, `--max-depth`, `--on-cycle`, `--rng-mode`, `--now`.
- `--json-errors`: emit structured JSON diagnostics on failure.

## Examples

### POST batches to an API

```bash
pfg persist ./app/models.py \
  --handler http-post \
  --handler-config '{"url": "https://api.example.com/fixtures", "headers": {"Authorization": "Bearer $TOKEN"}}' \
  --include app.schemas.User \
  --n 100 --batch-size 25 --preset realistic --seed 42
```

### Store payloads inside SQLite

```toml
[tool.pydantic_fixturegen.persistence.handlers.staging_db]
path = "pydantic_fixturegen.persistence.handlers:SQLiteJSONPersistenceHandler"
[tool.pydantic_fixturegen.persistence.handlers.staging_db.options]
database = "./artifacts/persist.db"
table = "users"
```

```bash
pfg persist ./models.py --handler staging_db --include app.models.User --n 200
```

### Custom handler via dotted path

```bash
pfg persist ./models.py \
  --handler mypkg.handlers:KafkaPublisher \
  --handler-config '{"brokers": "kafka:9092", "topic": "fixtures"}'
```

Handlers receive `PersistenceContext` objects (model metadata, batch size, config snapshot) before any batches stream through, so you can set up connections, transactions, or structured logging consistently across CLI runs.
