# `pfg verify`

## Capabilities
`pfg verify` recomputes the coverage manifest for the current source tree and compares it to an existing lockfile. It exits non-zero when drift is detected, making it ideal for CI jobs that must block merges unless the lockfile is refreshed.

## Typical use cases
- Gate pull requests until contributors rerun `pfg lock` after adding models or providers.
- Verify schema-driven coverage (JSON Schema or OpenAPI) in documentation repos.
- Detect accidental edits to the lockfile by re-running verification before publishing packages.

## Inputs & outputs
- **Target**: same choices as `pfg lock`—module path, `--schema`, or `--openapi` (with optional `--route`). Exactly one is required.
- **Lockfile**: `--lockfile/-f` path to the manifest you want to verify (defaults `.pfg-lock.json`).
- **Result**: prints “Coverage manifest verification succeeded.” on match. On mismatch, raises an `EmitError` containing a diff string in the `details` payload (emitted as JSON when `--json-errors` is active).

## Flag reference
- `--lockfile/-f`: lockfile location.
- `--include/-i`, `--exclude/-e`: glob filters.
- `--schema`, `--openapi`, `--route`: alternative targets (mutually exclusive with the positional path).
- `--ast`, `--hybrid`, `--timeout`, `--memory-limit-mb`: discovery guard rails.
- `--json-errors`: structured diagnostics.

## Example workflows
### CI verification
```bash
pfg verify ./app/models.py --lockfile .pfg-lock.json --include app.models.*
```
Exits `0` when the manifest matches; otherwise prints a diff and exits `1` so your CI job fails.

**Sample output**
```text
Coverage manifest verification succeeded.
```

### Verify OpenAPI coverage lockfile
```bash
pfg verify --openapi docs/openapi.yaml --lockfile ci/openapi-lock.json
```
Ensures the spec still matches the stored manifest.

**Sample output (mismatch)**
```text
ERROR: Coverage manifest mismatch.
diff:
  - coverage/models/User/address coverage changed 100% -> 92%
```

## Operational notes
- Lockfile loading is strict: missing files raise `EmitError` with a helpful message.
- When `--json-errors` is enabled the mismatch diff is attached to the JSON payload so you can parse it programmatically.
- Runtime guard rails like `--timeout`/`--memory-limit-mb` are recorded in the lockfile but ignored during comparison, so CI jobs can override them without forcing a lock refresh.
- Install plugin extras before verifying so plugin-provided providers match what was recorded when the lockfile was captured.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-verify)
- [Lock](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-lock.md)
- [Doctor](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-doctor.md)
