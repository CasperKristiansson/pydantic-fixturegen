# `pfg schema config`

## Capabilities
`pfg schema config` emits the JSON Schema that describes `pydantic-fixturegen`’s project configuration. Use it to validate `pyproject.toml`/YAML configs, power editor tooling, or document which keys are supported.

## Typical use cases
- Generate a schema for IDE validation when editing `pydantic-fixturegen.yaml`.
- Bundle the schema with internal tooling that renders forms or docs.
- Diff schema changes between releases.

## Inputs & outputs
- No target input is required—the command reads the bundled schema.
- `--out/-o`: optional path to write the schema. When omitted, the schema prints to stdout.
- `--pretty/--compact`: toggle indentation (pretty is default, producing human-readable output).

## Example workflows
### Write schema to docs folder
```bash
pfg schema config --out schema/config.schema.json --pretty
```
Creates (or overwrites) `schema/config.schema.json` with a pretty-printed schema.

**Sample output**
```text
Wrote schema/config.schema.json
```

### Pipe compact schema to a tool
```bash
pfg schema config --compact > /tmp/pfg-config-schema.json
```
Writes a minified schema to stdout.

**Sample output (stdout)**
```text
{"$schema":"http://json-schema.org/draft-07/schema#","title":"FixturegenConfig",...}
```

## Operational notes
- Parent directories are created automatically before writing.
- When printing to stdout, trailing whitespace is stripped so you can embed the schema in git patches without extra blank lines.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-schema)
- [Configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md)
