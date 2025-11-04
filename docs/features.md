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

## Tooling quality

- Works on Linux, macOS, Windows for Python 3.10–3.13.
- Atomic IO for all emitters to prevent partial artifacts.
- Ruff, mypy, pytest coverage ≥90% enforced in CI.
- Optional watch mode (`[watch]` extra), JSON logging, and structured diagnostics for CI integration.

Dive deeper into specific areas via [configuration](./configuration.md), [providers](./providers.md), [emitters](./emitters.md), and [security](./security.md).
