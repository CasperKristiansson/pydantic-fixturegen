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

## GitHub Actions recipe

The workflow below runs `pfg snapshot verify` across Python versions on Ubuntu. It assumes snapshots already live in the repo (for example under `artifacts/` and `tests/fixtures/`). Copy, adjust the paths, and wire it into your CI.

```yaml
name: Snapshot Verify

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ runner.os }}-${{ matrix.python-version }}-${{ hashFiles('pyproject.toml') }}
          restore-keys: |
            pip-${{ runner.os }}-${{ matrix.python-version }}-

      - name: Install fixturegen (dev extras)
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all-dev]"

      - name: Verify snapshots
        run: |
          pfg snapshot verify ./app/models.py \
            --json-out artifacts/users.json \
            --fixtures-out tests/fixtures/test_users.py \
            --seed 42 --freeze-seeds
```

Tips:

- Keep `--seed`/`--freeze-seeds` in the command to make CI deterministic.
- Add extra `--json-out`/`--fixtures-out` flags as needed; the step exits with code `1` when any snapshot drifts, failing the job automatically.
- If your pipeline regenerates artifacts first (e.g., via `pfg gen json`), run that step before verification so the snapshots in the repo are up to date.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-snapshot)
- [Snapshot write](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-write.md)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
