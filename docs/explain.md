# Explain: understand generation strategies

> Visualise how providers, presets, and policies compose before you trust generated data.

## Run explain

```bash
pfg gen explain ./models.py --tree --max-depth 2 --include app.models.User
```

- `--tree` prints an ASCII diagram that shows providers per field.
- `--json` emits the same data as structured JSON.
- `--max-depth` prevents runaway recursion with deeply nested models.
- `--include`/`--exclude` filter targets.
- `--json-errors` exposes issues such as failed imports with machine-readable payloads.

## Tree output

```text
User
 ├─ id: int ← number_provider(int)
 ├─ name: str ← string_provider
 ├─ nickname: Optional[str] ← union(p_none=0.25)
 └─ address: Address ← nested model
```

- Arrows identify the provider or strategy selected for each field.
- Inline annotations show policy tweaks such as `p_none`, presets, or union handling.
- Nested models appear under their parent field so you can trace recursion.

## JSON output

```bash
pfg gen explain ./models.py --json | jq '.models["app.models.User"].fields.nickname'
```

Sample payload:

```json
{
  "provider": "union",
  "policies": {"p_none": 0.25},
  "children": [
    {"provider": "string_provider", "weight": 0.75},
    {"provider": "none", "weight": 0.25}
  ]
}
```

- The JSON structure stays stable so you can parse it in CI.
- Use it to verify plugin overrides or preset applications by comparing expected providers.

## Tips

- Run `pfg gen explain` after updating `field_policies` or presets to confirm they apply.
- Combine with `--preset boundary` to check that edge-case exploration is active.
- Pipe the JSON output through linters or dashboards to track provider distribution over time.
- When working with untrusted models, pair explain runs with `pfg doctor` to inspect sandbox warnings.

Return to the [Cookbook](./cookbook.md) for recipes that use explain output to validate plugin behaviour.
