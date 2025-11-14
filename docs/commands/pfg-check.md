# `pfg check`

## Capabilities
`pfg check` validates discovery, configuration, and emitter destinations without generating artifacts. It is the quickest way to find misconfigured include/exclude globs, missing dependencies, or unwritable output paths before triggering a long generation run.

## Typical use cases
- Add to CI before `pfg gen` to fail fast on configuration mistakes.
- Run locally when wiring new output directories to confirm the process has permission to write there.
- Validate that AST/hybrid discovery finds at least one model under the current filters.

## Inputs & outputs
- **Target**: module path passed as a positional argument.
- **Outputs**: optional paths `--json-out`, `--fixtures-out`, `--schema-out`. When provided, fixturegen confirms that each path resolves to a writable location (parent directory exists, is a directory, and is writable, and the target is not a directory when it already exists).
- **Result**: prints “Configuration OK” plus the number of discovered models. Warnings surface on stderr. Non-zero exit indicates discovery or IO problems.

## Flag reference
- `--include/-i`, `--exclude/-e`: fully-qualified glob filters.
- `--ast`, `--hybrid`: choose discovery strategy.
- `--timeout`, `--memory-limit-mb`: guard rails for safe-import discovery.
- `--json-out`, `--fixtures-out`, `--schema-out`: optional emitter destinations to validate.
- `--json-errors`: structured diagnostics for automation.

## Example workflows
### Validate before running generators
```bash
pfg check ./app/models.py \
  --include app.models.* \
  --json-out artifacts/users.json \
  --fixtures-out tests/fixtures/test_users.py \
  --schema-out schema/users.json
```
Confirms the model glob resolves and every output parent directory exists and is writable.

**Sample output**
```text
Configuration OK
Discovered 12 model(s) for validation.
Emitter destinations verified.
Check complete. No issues detected.
```

### AST-only config check for flaky imports
```bash
pfg check ./app/models.py --ast --timeout 1 --memory-limit-mb 128
```
Runs in AST mode so imports never execute, useful when optional dependencies are missing locally.

**Sample output**
```text
Configuration OK
Discovered 12 model(s) for validation.
warning: import skipped; AST mode enabled
```

### Validate sibling output directories
```bash
TEMP_DIR=$(pwd)/tmp
pfg check ../temp/models.py \
  --timeout 30 --memory-limit-mb 256 \
  --json-out "$TEMP_DIR/out/check.json" \
  --fixtures-out "$TEMP_DIR/tests/fixtures/check.py" \
  --schema-out "$TEMP_DIR/schemas/check.json"
```
Helpful when you run the CLI from the repo root but want to confirm that paths under `../temp` (or another workspace) are writable before running heavy generators.

**Sample output**
```text
Configuration OK
Discovered 7 model(s) for validation.
Emitter destinations verified.
Check complete. No issues detected.
```

## Operational notes
- `pfg check` loads `pyproject.toml`/`pydantic-fixturegen.yaml` to validate configuration before discovery runs. Misconfigured values raise `ConfigError` which surfaces as `DiscoveryError` so CI sees a uniform failure type.
- When include/exclude filters select zero models the command raises `DiscoveryError` (“No models discovered.”) to ensure you catch typos early.
- Destination checks are conservative: they stop early if the parent directory is missing or lacks write permission so you can fix directories before re-running.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-check)
- [Configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md)
- [Security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md)
