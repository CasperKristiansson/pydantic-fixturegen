# Doctor & diagnostics: keep projects healthy

> Audit discovery coverage, diff generated artifacts, and validate configuration before you ship.

## `pfg doctor`

```bash
pfg doctor ./models.py --fail-on-gaps 0 --json-errors
```

- Scans models for uncovered fields, risky imports, and sandbox warnings.
- Discovery options match `pfg list`: `--ast`, `--hybrid`, `--include`, `--exclude`, `--timeout`, `--memory-limit-mb`.
- Use `--fail-on-gaps <N>` to exit with code `2` when more than `N` fields lack providers (set `0` to fail on any gap).
- `--json-errors` prints structured diagnostic payloads, enabling CI gating.

Review the report to see gap summaries grouped by type, recommended remediations, and severity levels.

## `pfg diff`

```bash
pfg diff ./models.py \
  --json-out artifacts/current.json \
  --fixtures-out tests/fixtures/test_models.py \
  --schema-out schema \
  --show-diff \
  --seed 42 \
  --freeze-seeds
```

- Regenerates artifacts in an isolated sandbox and compares them with existing files.
- Writes JSON summaries per artifact when you provide output paths; `--show-diff` streams unified diffs.
- Combine with frozen seeds to ensure deterministic comparisons.
- Exit code is non-zero when diffs are detected, making it ideal for pre-commit hooks.

## `pfg check`

```bash
pfg check ./models.py --json-errors --fixtures-out /tmp/fixtures.py
```

- Validates configuration, discovery, and emitter destinations without writing new artifacts.
- Mirrors `diff` output options (`--json-out`, `--fixtures-out`, `--schema-out`).
- Helpful for CI smoke tests before running heavier generation steps.

## Workflow tips

- Run `pfg doctor` locally when adding new models to reveal missing providers early.
- Use `pfg diff` in CI to enforce deterministic fixtures before merging pull requests.
- Insert `pfg check` into lightweight pipelines or commits to block invalid configuration without touching the filesystem.
- Pair diagnostics with structured [logging](./logging.md) for machine-readable auditing.
- When you see sandbox violations, review [security](./security.md) to adjust discovery mode or output paths.
