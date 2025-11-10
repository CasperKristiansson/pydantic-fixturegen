# `pfg gen examples`

## Capabilities
`pfg gen examples` loads an OpenAPI document, ingests the schemas referenced by your routes, generates deterministic model instances, and injects them back into the document under each component's `example` key. It is the CLI complement to embedding example payloads directly into OpenAPI specs without hand-writing JSON.

## Typical use cases
- Populate response/request examples before publishing to API Gateway, Stoplight, or ReDoc.
- Keep SDK reference docs synchronized with fixture seeds by regenerating examples in CI.
- Provide rich mocks for contract testing tools that read OpenAPI files.

## Inputs & outputs
- **Spec argument**: path to the OpenAPI YAML/JSON file to update.
- **Output**: `--out` destination file (required). The command never edits files in place; it always writes to the specified path.
- **Seed**: optional `--seed` ensures the generated examples match other artifacts.

## Flag reference
- `SPEC` (positional): OpenAPI document path.
- `--out/-o`: required destination file. Parent directories are created automatically.
- `--seed`: overrides the seed handed to the internal `InstanceGenerator` (defaults to random).

## Example workflows
### Add examples to every component schema
```bash
pfg gen examples openapi.yaml --out build/openapi.with-examples.yaml --seed 123
```
Copies the document, generates deterministic examples per referenced schema, and writes the enriched YAML to `build/...`.

**Sample output**
```text
[openapi_examples] schemas=24 seed=123
Examples written to build/openapi.with-examples.yaml
```

**Excerpt (`components.schemas.User.example`)**
```yaml
example:
  id: 203abed2-66ea-4d1c-8a8b-7bd55cba3e41
  email: avery@example.org
  created_at: '2025-11-08T12:00:00Z'
```

### Overwrite the original spec in place

```bash
pfg gen examples openapi.json --out openapi.json --seed 202
```

Regenerates examples directly inside the source file (useful for CI automation when the spec lives in git).

**Sample git diff**
```diff
 components:
   schemas:
     Order:
       type: object
-      example: null
+      example:
+        id: 8df5c2fa-98e1-4a34-a842-6a6b04fc91ed
+        total_cents: 1999
+        status: CAPTURED
```

## Operational notes
- Requires the `openapi` extra because the ingester relies on PyYAML and datamodel-code-generator.
- The command ingests schemas via `SchemaIngester` and uses `InstanceGenerator` so presets, overrides, and validator behavior mirror the main generators.
- Existing `example` keys are overwritten. Commit both the original and regenerated specs in source control to track changes.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-examples)
- [Explain](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/explain.md)
- [Output paths](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md)
