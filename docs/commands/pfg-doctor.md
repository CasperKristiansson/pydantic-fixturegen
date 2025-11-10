# `pfg doctor`

## Capabilities
`pfg doctor` audits model coverage, provider assignments, sandbox warnings, and strategy gaps. It can inspect Python modules, standalone JSON Schemas, or OpenAPI documents (with optional route filters). Reports include per-model coverage ratios, field-level gap descriptions, and aggregated summaries grouped by missing provider type.

## Typical use cases
- Enforce a minimum coverage target in CI via `--fail-on-gaps`.
- Diagnose why a field still falls back to `faker.lorem` despite custom providers.
- Inspect OpenAPI specs to confirm referenced schemas are fully covered before generating examples.
- Surface sandbox warnings (unsafe imports, missing dependencies) without running emitters.

## Inputs & outputs
- **Targets**: choose exactly one of:
  - Module path (positional argument).
  - `--schema PATH` for JSON Schema ingestion.
  - `--openapi PATH` optionally combined with `--route` filters such as `"GET /users"`.
- **Output**: human-readable text with per-model sections and a gap summary. Warnings print to stderr. Use `--json-errors` if you need machine-readable failures.

## Flag reference
- `--include/-i`, `--exclude/-e`: glob filters applied after target preparation.
- `--schema`, `--openapi`, `--route`: target selection options (mutually exclusive with the positional module path).
- `--ast`, `--hybrid`, `--timeout`, `--memory-limit-mb`: discovery guard rails identical to other commands.
- `--fail-on-gaps`: exit with code `2` when uncovered error-level fields exceed the provided threshold. Perfect for CI gating.
- `--json-errors`: emit structured diagnostics (includes warnings, issues, and details) instead of text.

## Example workflows
### Module audit with CI gate
```bash
pfg doctor ./app/models.py \
  --include app.models.* \
  --fail-on-gaps 0
```
Fails if *any* error-level gap remains, ensuring every field has a provider before merging.

**Sample output**
```text
Model app.models.User (coverage 12/12)
Model app.models.Order (coverage 15/15)
Gap summary: 0 error fields, 0 warning fields
```

### Analyze an OpenAPI document by route
```bash
pfg doctor --openapi openapi.yaml --route "POST /orders" --route "GET /users"
```
Ingests the spec, isolates schemas referenced by the listed routes, and audits them without importing your application code.

**Sample output**
```text
warning: app.schemas.LegacyOrder has 2 uncovered fields
Gap summary:
  DecimalStrategyMissing (error) -> 2 fields (Order.total, Order.discount)
```

## Operational notes
- When targeting schemas or OpenAPI, the command ingests the document into a temporary module and automatically seeds `--include` with the component names referenced by the selection.
- Reports list provider names, describe why a field lacks coverage (`Strategy missing for Decimal`, `Extra type not registered`, etc.), and show remediation hints pulled from the provider registry.
- The plugin manager loads before audits, so custom providers registered via entry points are evaluated as well.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-doctor)
- [Coverage + doctor reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/doctor.md)
- [Security & sandbox warnings](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md)
