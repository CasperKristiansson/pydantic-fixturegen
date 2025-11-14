# `pfg coverage`

`pfg coverage` inspects your models (Pydantic v2, stdlib `@dataclass`, or `TypedDict`) and prints a deterministic coverage dashboard. It reuses the same strategy builder as the generators, so the report reflects heuristics, overrides, and provider defaults exactly as `pfg gen ...` would.

## Capabilities
- Count fields that rely purely on heuristics, overrides, or fall back to generic providers.
- Highlight unused override patterns and relation links that reference missing models/fields.
- Emit human-readable tables **and** machine-friendly JSON via `--format json` for CI pipelines.
- Gate pull requests with `--fail-on heuristics|relations|overrides|any` when risks are detected.

## Key flags
- `target` (argument): module path containing supported models.
- `--include/-i`, `--exclude/-e`: wildcard filters for fully-qualified model names.
- `--ast` / `--hybrid`: control discovery method (AST-only or AST+safe-import hybrid).
- `--timeout`, `--memory-limit-mb`: caps for the safe-import subprocess.
- `--format text|json`: switch between console output and JSON (default `text`).
- `--fail-on <mode>`: exit with code 2 when risks are present (`none`, `heuristics`, `relations`, `overrides`, `any`).

## Example (text)
```bash
pfg coverage ./app/models.py --include app.schemas.*
```
```
Model: app.schemas.order.Order
  Coverage: 7/8 fields (88%)
  Providers:
    - identifier.uuid: 2
    - string.basic: 3
    - number.default: 2
  Heuristic fields: order_uuid
  Override matches: total_cents
  Uncovered fields: legacy_token

Summary:
  Models: 3
  Fields: 24 (covered=22, 92% deterministic)
  Heuristic fields: 3
  Override matches: 4
  Uncovered fields: 2
  Unused overrides: 1
  Relation issues: 1

Heuristic-only fields:
  - app.schemas.order.Order.order_uuid (provider=identifier.uuid)

Unused overrides:
  - model=app.schemas.* field=*_shadow (no matches)

Relation issues:
  - app.schemas.audit.Audit.event_id -> app.schemas.event.Event.id: source field 'event_id' not found
```

## Example (JSON + CI gating)
```bash
pfg coverage ./app/models.py --format json --fail-on overrides --out coverage.json
```
Abridged payload:
```json
{
  "models": [
    {
      "name": "app.schemas.order.Order",
      "coverage": {
        "covered": 7,
        "total": 8,
        "percent": 87.5
      },
      "heuristic_fields": ["order_uuid"],
      "override_fields": ["total_cents"],
      "uncovered_fields": ["legacy_token"],
      "provider_counts": {
        "identifier.uuid": 2,
        "number.default": 2,
        "string.basic": 3,
        "<unassigned>": 1
      }
    }
  ],
  "summary": {
    "models": 3,
    "fields": 24,
    "covered_fields": 22,
    "coverage_percent": 91.67,
    "heuristic_fields": 3,
    "override_matches": 4,
    "uncovered_fields": 2
  },
  "unused_overrides": [
    {
      "model_pattern": "app.schemas.*",
      "field_pattern": "*_shadow"
    }
  ],
  "relation_issues": [
    {
      "relation": "app.schemas.audit.Audit.event_id",
      "target": "app.schemas.event.Event.id",
      "reason": "source field 'event_id' not found"
    }
  ]
}
```
Exit code is `2` whenever the requested `--fail-on` category contains entries, which makes it simple to wire into CI/CD gates.

## Tips
- The report respects your `pyproject.toml`/`pfg.yaml` configuration (overrides, provider defaults, relations, heuristic toggles), so keep it near your generation commands in automation.
- Combine with `pfg doctor` for field-by-field remediation details; use the coverage JSON to feed dashboards or regression checks (`git diff coverage.json`).
- Need different privacy controls on demand? Add `--profile pii-safe` (or any available profile) so the report mirrors the redaction/masking settings you intend to ship.
- Prefer to avoid shell redirection? Use `--out coverage.json` with either text or JSON output and the CLI will write the report directly.
