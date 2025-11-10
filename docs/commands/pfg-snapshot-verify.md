# `pfg snapshot verify`

## Capabilities
`pfg snapshot verify` regenerates artifacts in-memory (JSON, fixtures, schema) and compares them to stored snapshots without writing to disk. It is the snapshot-friendly wrapper around the diff engine: if any artifact drifts, the command exits with an error so CI can fail fast.

## Typical use cases
- Run in CI to ensure committed artifacts remain up to date before allowing merges.
- Trigger from `pre-commit` hooks so contributors refresh snapshots when models change.
- Mix and match emitters (verify JSON + fixtures, skip schema, etc.).

## Inputs & outputs
- **Target**: module path supplied as a positional argument.
- **Snapshots**: provide one or more of `--json-out`, `--fixtures-out`, `--schema-out`. Each points at an existing file to verify.
- **Result**: prints “Snapshots verified.” when everything matches. On drift, raises `SnapshotAssertionError` with a diff summary and exits with code `1`.

## Flag reference
Most flags mirror `pfg diff`. Highlights:

**Discovery & determinism**
- `--include/-i`, `--exclude/-e`, `--ast`, `--hybrid`, `--timeout`, `--memory-limit-mb`.
- `--seed`, `--p-none`, `--now`, `--preset`, `--profile`, `--freeze-seeds`, `--freeze-seeds-file`, `--rng-mode`.
- `--respect-validators`, `--validator-max-retries`, `--link`.

**JSON snapshot options**
- `--json-out`: existing file.
- `--json-count`, `--json-jsonl`, `--json-indent`, `--json-orjson`, `--json-shard-size`.

**Fixtures snapshot options**
- `--fixtures-out`, `--fixtures-style`, `--fixtures-scope`, `--fixtures-cases`, `--fixtures-return-type`.

**Schema snapshot options**
- `--schema-out`, `--schema-indent`.

## Example workflows
### Verify JSON + fixtures in CI
```bash
pfg snapshot verify ./app/models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42 --freeze-seeds --preset boundary
```
Exits `0` when both artifacts are still current; prints diffs and exits `1` when drift occurs.

**Sample output (drift)**
```text
Snapshot mismatch for fixtures_out:
  tests/fixtures/test_users.py
Run `pfg snapshot write ...` to update snapshots.
```

### Verify schema snapshots only

```bash
pfg snapshot verify ./app/models.py \
  --schema-out schema/app.models.User.json \
  --schema-indent 2
```

Ensures the stored schema matches regenerated output without touching JSON or fixtures.

**Sample output**
```text
Snapshots verified.
```

## Operational notes
- At least one `--*-out` flag is required; otherwise the command raises `BadParameter`.
- Under the hood, `SnapshotRunner` reuses safe-import discovery (respecting AST/hybrid settings) so verification never mutates files.
- Use `pfg snapshot write` when you intentionally want to refresh snapshots after a failure.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-snapshot)
- [Snapshot write](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-write.md)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
