# `pfg gen explain` / `pfg explain`

## Capabilities
`pfg gen explain` (also exposed as top-level `pfg explain`) introspects every selected model, builds the underlying generation strategies, and renders them either as structured JSON or an ASCII tree. It is the fastest way to understand how providers, unions, custom types, and pluggy hooks will behave before generating artifacts.

## Typical use cases
- Audit complex field strategies to verify provider coverage or understand fallback behavior.
- Capture JSON output and feed it into docs, dashboards, or diff tooling.
- Render trees during code review to show how presets and overrides affect nested structures.

## Inputs & outputs
- **Target**: Python module containing the models to inspect.
- **Outputs**:
  - Default text report showing each model, field, provider, and coverage/gap status.
  - `--tree`: ASCII tree drawing strategy composition.
  - `--json`: machine-readable payload containing warnings and per-model strategy data (mutually exclusive with `--tree`).

## Flag reference
- `--include/-i`, `--exclude/-e`: filter fully-qualified model names.
- `--json`: emit JSON summary (includes warnings list and per-model strategy metadata).
- `--tree`: draw ASCII trees instead of tables.
- `--max-depth`: limit nested expansion depth (0 means top-level only). Useful when models recurse deeply.
- `--json-errors`: structured diagnostics when discovery fails or arguments conflict.

## Example workflows
### Text report for a subset of models
```bash
pfg explain ./app/models.py --include app.models.User,app.models.Order
```
Prints one report per model describing each field’s provider, coverage, and linked strategies.

**Sample output**
```text
Model app.models.User (coverage 8/8)
 ├─ id: UUID4Strategy (provider: uuid4)
 ├─ email: Faker.email (profile=realistic)
 └─ profile: DelegatedStrategy -> CustomProfileProvider

Model app.models.Order (coverage 12/13)
 └─ gaps:
    - amount: Strategy missing for Decimal -> add NumberProvider
```

### JSON export for docs tooling
```bash
pfg explain ./app/models.py --json --max-depth 2 > build/strategy-report.json
```
Writes machine-readable output (warnings + strategy tree) capped at depth 2 for embedding elsewhere.

**Sample output excerpt**
```json
{
  "warnings": [],
  "models": [
    {
      "name": "User",
      "fields": [
        {"name": "id", "strategy": "UUID4Strategy"},
        {"name": "created_at", "strategy": "DatetimeStrategy"}
      ]
    }
  ]
}
```

## Operational notes
- `--json` and `--tree` cannot be combined; the CLI enforces this early.
- Reports call into the same `StrategyBuilder` used by generation, so plugin-provided strategies and registry tweaks appear here too.
- When include/exclude filters yield no models, the command prints “No models discovered.” and exits successfully—use CI wrappers to treat that as a failure if needed.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-explain)
- [Strategy internals](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/strategies.md)
- [Doctor](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/doctor.md)
