# Logging: capture structured events

> Emit JSON logs for automation and tune verbosity without losing determinism.

## Enable structured logging

```bash
pfg --log-json gen json ./models.py --out ./out/users.json
```

- Combine with `--verbose` (`-v`) to expose debug events or `--quiet` (`-q`) to restrict output.
- Logs are emitted as single-line JSON objects suitable for ingestion by log processors.

## Event schema

```jsonc
{
  "timestamp": "2024-10-24T20:17:30",
  "level": "info",
  "event": "json_generation_complete",
  "message": "JSON generation complete",
  "context": {
    "files": ["/tmp/out.json"],
    "count": 3
  }
}
```

- `timestamp` uses ISO 8601 in UTC.
- `level` reflects the current verbosity after applying `-v`/`-q`.
- `event` stays stable; rely on it instead of `message` for machine checks.
- `context` carries command-specific metadata (paths, counts, diff stats, warnings).

## Event highlights

- `json_generation_started` / `json_generation_complete`
- `fixtures_emitted`, `fixtures_skipped`
- `schema_written`
- `constraint_report` (includes details on fields that failed constraints)
- `seed_freeze_stale` (missing entries are silent)
- `sandbox_timeout`, `sandbox_violation`

Inspect logs by piping to `jq`:

```bash
pfg --log-json gen fixtures ./models.py --out tests/fixtures/test_users.py | jq '.event'
```

Use structured logs alongside [doctor diagnostics](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/doctor.md) and [presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/presets.md) to maintain observability across CI runs.
