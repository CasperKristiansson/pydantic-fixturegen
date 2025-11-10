# `pfg gen openapi`

## Capabilities
`pfg gen openapi` ingests an OpenAPI 3.x document, selects component schemas (optionally filtered by `--route`), materializes temporary Pydantic models via the schema ingester, and then runs the JSON generator against those models. It is the fastest way to turn your API spec into real example payloads that match presets, privacy profiles, and validator rules.

## Typical use cases
- Generate JSON snapshots for each schema referenced by a route in your OpenAPI document.
- Produce deterministic payloads that backfill `components.schemas.*.example` values or SDK fixtures.
- Validate that schema-driven generation still respects presets/freeze files before running full model discovery.

## Inputs & outputs
- **Spec**: `--spec` positional argument pointing to a YAML or JSON OpenAPI file.
- **Routes**: `--route "METHOD /path"` optionally limits generation to specific endpoints. Without it all referenced schemas are processed.
- **Output**: `--out` template (must include `{model}` when more than one schema is selected). Uses the same templating engine as `pfg gen json`.

## Flag reference
**JSON emission options**
- `--n`, `--jsonl`, `--indent`, `--orjson`, `--shard-size`: identical to `pfg gen json`.
- `--seed`, `--now`, `--freeze-seeds`, `--freeze-seeds-file`, `--preset`, `--profile`.
- `--respect-validators`, `--validator-max-retries`, `--max-depth`, `--on-cycle`, `--rng-mode`.

**OpenAPI selection**
- `--route`: repeatable filter accepting `METHOD /path` syntax (case-insensitive). Under the hood the CLI parses the spec, identifies referenced schemas for those routes, and only exports those components.

**Diagnostics**
- `--json-errors`: surface structured errors if the document is invalid, the output template is missing `{model}`, or OpenAPI parsing fails.

## Example workflows
### Emit JSON per schema under an `openapi/` directory
```bash
pfg gen openapi openapi.yaml \
  --out openapi/{model}.json \
  --n 25 --jsonl --seed 99 --preset boundary
```
Builds deterministic JSONL payloads for every component schema and writes each file under `openapi/SchemaName.json`.

**Sample output**
```text
[openapi_parse] spec=openapi.yaml routes=ALL schemas=32
[json_emitted] path=openapi/User.json lines=25
[json_emitted] path=openapi/Order.json lines=25
```
**Excerpt from `openapi/User.json`**
```json
{
  "model": "app.schemas.User",
  "payloads": [
    {
      "id": "a4210f94-8a8c-4e53-9341-bab0d27d8df4",
      "email": "rivera@example.com",
      "created_at": "2025-11-08T12:00:00Z"
    },
    ...
  ]
}
```

### Limit output to selected routes
```bash
pfg gen openapi openapi.yaml \
  --route "GET /users" --route "POST /orders" \
  --out artifacts/{model}/{timestamp}.json --profile pii-safe
```
Filters down to schemas referenced by the `GET /users` and `POST /orders` operations.

**Sample output**
```text
[openapi_parse] routes=['GET /users','POST /orders'] schemas=['UserResponse','CreateOrder']
[json_emitted] path=artifacts/UserResponse/2024-06-01T12-00-00Z.json
[json_emitted] path=artifacts/CreateOrder/2024-06-01T12-00-00Z.json
```
**Excerpt from `artifacts/CreateOrder/2024-06-01T12-00-00Z.json`**
```json
{
  "body": {
    "sku": "SKU-000142",
    "quantity": 2,
    "shipping": {
      "street": "920 Fixture Ave",
      "city": "Testville",
      "postal_code": "42424"
    }
  }
}
```

## Operational notes
- When the selection contains multiple schemas but `--out` lacks `{model}`, the command fails early with a hint so you do not overwrite files.
- Schemas are ingested via a fingerprinted temporary module; repeated runs with the same spec reuse cached modules for speed.
- Logs show the fingerprint, selected schema names, and constraint summaries for each generated file. Use verbose logging (`-v`) to capture the resolved `include` filter created internally (for example `*.UserResponse`).

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-openapi)
- [Explain / strategy trees](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/explain.md)
- [Configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md)
