# Concepts: why pydantic-fixturegen exists

> Ground yourself in the principles behind deterministic fixture generation.

## Deterministic by design

- Seeds cascade across Python `random`, Faker, and optional NumPy RNGs.
- Freeze files (`.pfg-seeds.json`) store per-model seeds so regeneration stays identical everywhere.
- Metadata banners capture seed, version, and digest to prove provenance.

## Sandbox-first safety

- Untrusted models run inside a safe-import sandbox that blocks network calls, jails filesystem writes, and caps memory.
- Exit code `40` signals timeouts; diagnostics flag risky imports.
- Discovery supports AST-only mode when you cannot run user code at all.

## CLI-first workflow

- `pfg` wraps every task: list models, generate JSON, emit fixtures, diff outputs, check configs, explain strategies, and run doctors.
- Commands share consistent flag names (`--include`, `--exclude`, `--seed`, `--preset`) to reduce context switching.
- Watch mode (`[watch]` extra) keeps artifacts in sync during development.

## Extensibility with Pluggy

- Provider registry accepts new generators via `pfg_register_providers`.
- Strategies can be adjusted per-field through `pfg_modify_strategy`.
- Emitters can be replaced or augmented with `pfg_emit_artifact`.
- Entry points allow third-party packages to ship plugins without forking.

## Atomic, auditable output

- Emitters write to temp files and rename into place, eliminating partial artifacts.
- JSON and schema content uses sorted keys and trailing newlines for clean diffs.
- Fixture modules store digest metadata and align with formatters like Ruff/Black.

Keep these concepts in mind as you explore the [quickstart](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md), dive into [configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md), or extend the system via [providers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md).
