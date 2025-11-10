# `pfg gen schema`

## Capabilities
`pfg gen schema` produces JSON Schema files for your models. Unlike `pfg schema config`, this command runs inside the generation pipeline so schemas share the same include/exclude filters, privacy profile, and watch mode as JSON/fixtures. It is ideal for bundling typed contracts alongside generated data.

## Typical use cases
- Ship per-model schemas with SDKs or documentation sites.
- Validate how privacy profiles (for example `pii-safe`) transform schemas before regenerating artifacts.
- Run in watch mode while iterating on models to immediately inspect schema diffs.

## Inputs & outputs
- **Target**: Python module containing models.
- **Output**: templated `--out` path. Include `{model}` to emit one file per model, or point at a directory to leverage templating (for example `schema/{model}.json`).

## Flag reference
- `--out/-o`: required path or template.
- `--indent`: override JSON indentation (default derived from config).
- `--include/-i`, `--exclude/-e`: select which models to emit.
- `--profile`: apply privacy bundles prior to schema generation, ensuring sensitive fields are masked/excluded the same way as JSON output.
- `--watch` + `--watch-debounce`: keep the command running and regenerate schemas when any watched file changes.
- `--json-errors`: (global) surface structured diagnostics when schema emission fails (for example due to invalid output templates).

## Example workflows
### Emit per-model schemas with privacy profile
```bash
pfg gen schema ./app/models.py \
  --out schema/{model}.json --include app.models.* \
  --profile pii-safe --indent 2
```
Writes each schema under `schema/`, ensuring PII-sensitive fields reflect the `pii-safe` bundle.

**Sample output**
```text
[schema_emit] path=schema/app.models.User.json bytes=2417
[schema_emit] path=schema/app.models.Address.json bytes=1095
profile=pii-safe indent=2
```

**Excerpt (`schema/app.models.User.json`)**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "User",
  "type": "object",
  "properties": {
    "email": {"type": "string", "format": "email"},
    "profile": {
      "type": "object",
      "properties": {
        "marketing_opt_in": {"type": "boolean"},
        "timezone": {"type": "string"}
      }
    }
  }
}
```

### Watch and regenerate a directory index
```bash
pfg gen schema ./app/models.py --out schema/index.json --watch
```
Keeps `schema/index.json` up to date as you tweak models.

**Sample output**
```text
[watch] tracking=/repo/app/models.py,/repo/schema/index.json
Regenerated schema/index.json (models=17)
```

## Operational notes
- Watch mode tracks the module tree plus the resolved output directory so new files trigger reruns.
- When templates create directories dynamically, fixturegen watches the parent folder to rebuild path previews safely.
- Constraint summaries for schema emission are logged at debug level (helpful when diagnosing why a field is missing).

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-schema)
- [Output paths](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md)
- [Privacy profiles](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md#profiles)
