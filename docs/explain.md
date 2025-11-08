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
 ├─ email: str ← provider identifier.email (p_none=0.0)
 │   Heuristic: string-email (confidence=0.95)
 ├─ nickname: Optional[str] ← union(p_none=0.25)
 └─ address: Address ← nested model
```

- Arrows identify the provider or strategy selected for each field.
- Inline annotations show policy tweaks such as `p_none`, presets, or union handling.
- Nested models appear under their parent field so you can trace recursion.
- Recursive fields now show a `Cycle policy` line (matching `--on-cycle` / `[cycle_policy]`), so you can see whether fixturegen will reuse existing data, emit stubs, or drop to null when a cycle is detected.
- When a heuristic rule fires, the provider line is followed by the rule name and confidence score so you can see why a string field was treated as an email, slug, ISO country code, etc.

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
- Heuristic metadata is reported alongside every provider: `strategy.heuristic` contains the rule name, description, confidence score, and the signals that caused the match (field names, metadata tags, constraint patterns, etc.).

Example snippet for an auto-detected email field:

```json
{
  "provider": "identifier.email",
  "heuristic": {
    "rule": "string-email",
    "confidence": 0.95,
    "signals": ["keyword:email"],
    "provider_type": "email"
  }
}
```

## Heuristic provenance

- The heuristic engine inspects field names, aliases, metadata, and regex/length constraints before defaulting to type-based providers. Rules are priority-ordered and pluggable via `pfg_register_heuristics`.
- Use `pfg gen explain --json` to capture rule decisions in CI or documentation; the tree/text view prints the rule name and confidence inline.
- Disable heuristics globally via `[tool.pydantic_fixturegen.heuristics] enabled = false` or `PFG_HEURISTICS__ENABLED=false` when you prefer explicit field policies.

## Tips

- Run `pfg gen explain` after updating `field_policies` or presets to confirm they apply.
- Combine with `--preset boundary` to check that edge-case exploration is active.
- Pipe the JSON output through linters or dashboards to track provider distribution over time.
- When working with untrusted models, pair explain runs with `pfg doctor` to inspect sandbox warnings.

Return to the [Cookbook](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md) for recipes that use explain output to validate plugin behaviour.
