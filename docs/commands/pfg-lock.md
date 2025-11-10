# `pfg lock`

## Capabilities
`pfg lock` computes a coverage manifest (discovery options, provider assignments, coverage ratios, gap summaries) and writes it to a lockfile (default `.pfg-lock.json`). Pair it with `pfg verify` to detect coverage regressions in CI.

## Typical use cases
- Freeze coverage state for a release branch and fail future builds when coverage drifts.
- Share a manifest with compliance teams showing exactly which models/fields are covered.
- Track discovery settings (ast/import/hybrid, include/exclude globs) under version control.

## Inputs & outputs
- **Target**: choose one of a module path, `--schema`, or `--openapi` (with optional `--route`). Exactly one must be provided.
- **Output**: JSON lockfile at `--lockfile` (defaults `.pfg-lock.json`). When `--force` is false and the lockfile already matches the current manifest, the command prints “Coverage lockfile already up to date” and exits without rewriting.

## Flag reference
- `--lockfile/-f`: destination path.
- `--force`: always rewrite the lockfile even if no changes were detected.
- `--include/-i`, `--exclude/-e`: glob filters.
- `--schema`, `--openapi`, `--route`: alternate targets (mutually exclusive with positional path).
- `--ast`, `--hybrid`, `--timeout`, `--memory-limit-mb`: discovery guard rails.
- `--json-errors`: structured diagnostics.

## Example workflows
### Write/update the default lockfile
```bash
pfg lock ./app/models.py --lockfile .pfg-lock.json --include app.models.*
```
Generates a manifest and writes it to `.pfg-lock.json`, creating directories if needed.

**Sample output**
```text
Wrote coverage lockfile to /repo/.pfg-lock.json
Models: 18, coverage ratio: 100%
```

### Lock coverage for an OpenAPI spec
```bash
pfg lock --openapi docs/openapi.yaml --route "GET /users" --lockfile ci/openapi-lock.json
```
Analyzes schemas referenced by the specified routes and records the resulting manifest.

**Sample output**
```text
Wrote coverage lockfile to /repo/ci/openapi-lock.json
Schemas locked: ['UserResponse', 'PagedUsers']
```

## Operational notes
- Manifests include plugin-derived providers, so install your plugin extras before running `pfg lock`.
- The CLI compares the new manifest to the existing file when `--force` is false; this makes the command idempotent in CI.
- Lockfiles serialize with indentation for readability. Treat them like code: review changes carefully to spot missing providers.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-lock)
- [Doctor](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-doctor.md)
- [Verify](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-verify.md)
