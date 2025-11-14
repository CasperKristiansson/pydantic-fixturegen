# `pfg diff`

## Capabilities
`pfg diff` regenerates artifacts in-memory (JSON, pytest fixtures, schemas) and compares them to what’s on disk. It is the CLI-friendly equivalent of running `pytest --pfg-update-snapshots` in “verify” mode, with granular control over which emitters participate and how diffs are displayed.

## Typical use cases
- Detect drift in committed JSON fixtures during CI.
- Compare regenerated pytest modules to on-disk versions before deciding whether to refresh snapshots.
- Validate `--link`, `--preset`, or `--freeze-seeds` changes without writing files.

## Inputs & outputs
- **Target**: module path to regenerate from.
- **Outputs**: specify any combination of `--json-out`, `--fixtures-out`, `--schema-out`. Each path points at the existing artifact to compare against. If none are provided the command exits with an error because there is nothing to diff.
- **Result**: prints per-artifact reports; when `--show-diff` is set it streams unified diffs to stdout. Non-zero exit codes indicate differences or errors (use exit status in CI).

## Flag reference
**Discovery guards**
- `--include/-i`, `--exclude/-e`, `--ast`, `--hybrid`, `--timeout`, `--memory-limit-mb`.

**Determinism**
- `--seed`, `--p-none`, `--now`, `--preset`, `--profile`, `--rng-mode`.
- `--freeze-seeds`, `--freeze-seeds-file` (locks per-model seeds while diffing).
- `--link` ensures regenerated relations mirror the original artifact policy.

**Validator + overrides**
- `--respect-validators`, `--validator-max-retries`.
- `-O/--override` (available indirectly via `diff` importing generation helpers) to match ad-hoc fixture overrides when diffing.

**JSON diff options**
- `--json-out`: path to the existing JSON/JSONL artifact.
- `--json-count`: how many samples to regenerate (default 1).
- `--json-jsonl`: treat the artifact as JSONL instead of JSON.
- `--json-indent`, `--json-orjson`, `--json-shard-size`: override emitter settings.

**Fixtures diff options**
- `--fixtures-out`: existing pytest module path.
- `--fixtures-style`, `--fixtures-scope`, `--fixtures-cases`, `--fixtures-return-type`: ensure regenerated fixtures match the style of the artifact you’re checking.

**Schema diff options**
- `--schema-out`: JSON schema path to compare.
- `--schema-indent`: override indentation.

**Presentation**
- `--show-diff`: stream unified diffs on mismatches (otherwise you’ll only see summary messages).
- `--json-errors`: return structured diagnostics for automation.

## Example workflows
### Check JSON + fixtures in CI
```bash
pfg diff ./app/models.py \
  --json-out artifacts/users.json --json-jsonl \
  --fixtures-out tests/fixtures/test_users.py \
  --seed 42 --freeze-seeds --preset boundary \
  --show-diff
```
Regenerates both emitters, compares them to disk, and prints unified diffs when differences arise.

**Sample output**
```text
[json_diff] unchanged artifacts/users.json
[fixtures_diff] changed tests/fixtures/test_users.py
@@ -42,7 +42,7 @@
-        "first_name": "Ivy"
+        "first_name": "Ingrid"
constraint_summary: warnings=0 fields=18 constrained=5
exit status: 1
```

### Tight discovery with hybrid mode
```bash
pfg diff ./app/models.py --hybrid --timeout 2 --memory-limit-mb 128 --json-out artifacts/orders.json
```
Limits import cost during CI while still validating artifacts.

**Sample output**
```text
[discovery] method=hybrid timeout=2.0 memory=128 MB
[json_diff] unchanged artifacts/orders.json
```

### Absolute paths + template outputs
```bash
TEMP_DIR=$(pwd)/tmp
pfg diff ../temp/models.py \
  --include models.User \
  --json-out "$TEMP_DIR/snapshots/users.json" \
  --fixtures-out "$TEMP_DIR/snapshots/fixtures.py" \
  --seed 42 --freeze-seeds --timeout 60 --memory-limit-mb 512
```
Demonstrates how to diff artifacts that live outside the current working directory now that path templates can resolve `../` segments. The command regenerates both JSON and fixture artifacts using the same seeds and reports `0` when they match.

**Sample output**
```text
[json_diff] unchanged /repo/tmp/snapshots/users.json
[fixtures_diff] unchanged /repo/tmp/snapshots/fixtures.py
All compared artifacts match.
```

## Operational notes
- Exit code `0` means “no drift”; `1` means either a difference was detected or an unrecoverable error occurred. Gate CI on `pfg diff` by checking for `0` explicitly.
- Constraint summaries are attached to diff outputs so you can see which fields failed validation or had provider warnings.
- When `--json-errors` is enabled, the diff report surfaces as a JSON payload containing per-artifact status, making it easy to upload to CI dashboards.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-diff)
- [Snapshots](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-verify.md)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
