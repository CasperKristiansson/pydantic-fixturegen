# Features: what pydantic-fixturegen delivers

> Explore capabilities across discovery, generation, emitters, security, and tooling quality.

## Discovery

- AST and safe-import discovery with optional hybrid mode.
- Include/exclude glob patterns, `--public-only`, and discovery warnings.
- Structured error payloads (`--json-errors`) with taxonomy code `20`.
- Sandbox controls for timeout and memory limits.

## Generation engine

- Depth-first instance builder with recursion limits and constraint awareness.
- Deterministic seeds cascade across Python `random`, Faker, and optional NumPy.
- NumPy array provider with configurable dtype/shape caps (enable the `numpy` extra).
- Numeric distribution controls (uniform, normal, spike) for ints/floats/decimals via the `[numbers]` configuration block or `PFG_NUMBERS__*` env vars.
- Relation-aware generation: declarative `relations` config / `--link` CLI flags reuse pools of generated models so foreign keys and shared references stay in sync, and JSON bundles can include related models via `--with-related`.
- Optional validator retries (`respect_validators` / `validator_max_retries`) that keep re-generation deterministic while surfacing structured diagnostics when model validators never converge.
- Field policies for enums, unions, and optional probabilities (`p_none`).
- Configuration precedence: CLI → environment (`PFG_*`) → pyproject/YAML → defaults.

## Emitters

- JSON/JSONL with optional `orjson`, sharding, and metadata banners.
- Pytest fixtures with deterministic parametrisation, configurable style/scope, and atomic writes.
- JSON Schema emission with sorted keys and trailing newline stability.

## Plugins and extensibility

- Pluggy hooks: `pfg_register_providers`, `pfg_modify_strategy`, `pfg_emit_artifact`.
- Entry-point discovery for third-party packages.
- Strategy and provider registries open for customization via Python API or CLI.

## Security and sandboxing

- Safe-import sandbox blocking network access, jailing filesystem writes, and capping memory.
- Exit code `40` for timeouts, plus diagnostic events for violations.
- `pfg doctor` surfaces risky imports and coverage gaps.

## Privacy profiles

- Built-in `pii-safe` and `realistic` bundles exposed via `--profile` or `[tool.pydantic_fixturegen].profile`.
- `pii-safe` masks identifiers with `example.com` emails, `example.invalid` URLs, reserved IP ranges, and deterministic test card numbers while nudging optional PII fields toward `None`.
- `realistic` restores richer Faker/identifier output and keeps optional contact fields populated for staging data.
- Profiles compose with presets and explicit overrides, so you can layer additional field policies or configuration on top.

## Tooling quality

- Works on Linux, macOS, Windows for Python 3.10–3.13.
- Atomic IO for all emitters to prevent partial artifacts.
- Ruff, mypy, pytest coverage ≥90% enforced in CI.
- Optional watch mode (`[watch]` extra), JSON logging, and structured diagnostics for CI integration.

Dive deeper into specific areas via [configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md), [providers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md), [emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md), and [security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md).
