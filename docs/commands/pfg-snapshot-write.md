# `pfg snapshot write`

## Capabilities
`pfg snapshot write` regenerates artifacts and writes them back to disk, refreshing stored snapshots in place. It uses the same configuration as `pfg snapshot verify` but sets the update mode to `UPDATE`, so unchanged files remain untouched while drifted files are atomically rewritten.

## Typical use cases
- Refresh JSON/fixture/schema snapshots after intentional model changes.
- Provide a single command for contributors to run locally before pushing updates.
- Automate snapshot refreshes inside release pipelines after bumping presets/profiles.

## Inputs & outputs
- **Target**: module path (positional argument).
- **Outputs**: one or more of `--json-out`, `--fixtures-out`, `--schema-out`. These files are regenerated on disk when drift is detected.
- **Result**: prints “Snapshots refreshed.” when files were updated, or “Snapshots already up to date.” if nothing changed.

## Flag reference
Same as `pfg snapshot verify`:
- Discovery/determinism flags (`--include`, `--seed`, `--preset`, `--profile`, `--link`, etc.).
- JSON snapshot knobs (`--json-count`, `--json-jsonl`, `--json-indent`, `--json-orjson`, `--json-shard-size`).
- Fixture knobs (`--fixtures-style`, `--fixtures-scope`, `--fixtures-cases`, `--fixtures-return-type`).
- Schema knobs (`--schema-indent`).

## Example workflows
### Refresh everything after a model change
```bash
pfg snapshot write ./app/models.py \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --schema-out schema/users.json \
  --seed 42 --preset boundary
```
Regenerates all three artifacts, overwriting the files with the new deterministic output.

**Sample output**
```text
Updated artifacts/users.json
Updated tests/fixtures/test_users.py
schema/users.json already up to date
Snapshots refreshed.
```

### Refresh fixtures only with custom style

```bash
pfg snapshot write ./app/models.py \
  --fixtures-out tests/fixtures/test_users.py \
  --fixtures-style class \
  --fixtures-scope module \
  --fixtures-cases 2
```

**Sample output**
```text
Updated tests/fixtures/test_users.py
Snapshots refreshed.
```

## Operational notes
- Exit code is always `0` when generation succeeds, even if files were updated. Errors raise `SnapshotAssertionError`/`PFGError` and exit `1`.
- The runner only touches files that actually changed. Combined with `git diff` you can easily review which artifacts were rewritten.
- Use `--freeze-seeds` if you want the refresh to preserve per-model seeds stored in `.pfg-seeds.json`.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-snapshot)
- [Snapshot verify](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-verify.md)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
