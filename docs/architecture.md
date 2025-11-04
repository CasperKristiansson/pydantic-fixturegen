# Architecture: how the pipeline fits together

> Understand the stages that turn Pydantic models into deterministic artifacts.

```text
Models
  ↓
Discovery (AST ⟷ Safe-Import Sandbox)
  ↓
Strategies (policies + presets + plugins)
  ↓
ProviderRegistry (built-ins + pfg_register_providers)
  ↓
Instance Builder (deterministic seeds)
  ↓
Emitters (JSON | Fixtures | Schema, atomic IO)
  ↓
Artifacts with metadata (seed/version/digest)
```

## Stage breakdown

- **Discovery**: Collects model metadata using AST, sandboxed imports, or hybrid mode. Emits warnings when imports misbehave.
- **Strategies**: `StrategyBuilder` summarises field constraints, applies presets, and calls plugin hooks to adjust strategy objects.
- **Provider registry**: Supplies concrete value generators. Plugins can register additional providers or override defaults.
- **Instance builder**: Cascades deterministic seeds across Faker and optional NumPy, respecting `p_none`, enum, and union policies.
- **Emitters**: Write JSON/JSONL, pytest fixtures, and schema files atomically, templating output paths as needed.
- **Metadata**: Banners and logs record seed, generator version, digests, style, scope, and constraint summaries.

## Plugin touchpoints

- `pfg_register_providers` — add or replace providers before strategies run.
- `pfg_modify_strategy` — tweak per-field strategies after defaults are created.
- `pfg_emit_artifact` — intercept artifact writing; return `True` to skip the built-in emitter.

## Observability

- Structured logging (`--log-json`) mirrors each stage with stable event names.
- `pfg doctor` reports coverage metrics and sandbox issues after discovery and strategy building.
- Diff/check commands reuse the same pipeline to ensure comparisons match real generation.

For extension guidance, continue to [providers](./providers.md), [strategies](./strategies.md), or [emitters](./emitters.md).
