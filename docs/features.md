# Features: what pydantic-fixturegen delivers

> Explore capabilities across discovery, generation, emitters, security, and tooling quality.

## Discovery

- AST and safe-import discovery with optional hybrid mode.
- Include/exclude glob patterns, `--public-only`, and discovery warnings.
- Structured error payloads (`--json-errors`) with taxonomy code `20`.
- Sandbox controls for timeout and memory limits.

## Schema ingestion

- `pfg gen json --schema schema.json` ingests standalone JSON Schema documents (via `datamodel-code-generator`) and immediately reuses the cached module for generation, explain, and diff workflows.
- `pfg gen openapi spec.yaml --route "GET /users"` materialises OpenAPI 3.x components, isolates the schemas referenced by the selected routes, and emits a per-schema JSON sample (using `{model}` in your output template to fan out across operations).
- `pfg doctor --schema` / `--openapi` surface coverage gaps for schema-driven models, so you can spot unsupported field shapes before writing a single Python class.
- `pfg gen examples spec.yaml --out spec_with_examples.yaml` injects deterministic example payloads into every referenced schema/component, so your OpenAPI docs stay realistic without manual curation.
- Generated modules are cached under `.pfg-cache/schemas` keyed by the document fingerprint and selected routes, which keeps reruns instant while still regenerating when the source spec changes.

## FastAPI integration

- `pfg fastapi smoke app.main:app` inspects live FastAPI apps, generates deterministic request/response bodies with pydantic-fixturegen, and scaffolds a pytest suite that asserts every documented route returns a 2xx status and passes response-model validation.
- `pfg fastapi serve app.main:app --port 8050` spins up a mock server that mirrors your routes but responds with fixture-generated payloads—perfect for demos, contract-first development, or onboarding stakeholders before the real backend exists.
- Dependency injection hooks can be bypassed via `--dependency-override original=stub`, so auth/session providers or rate-limiters don’t block smoke tests and mock responses.
- Install the `fastapi` extra to pull in FastAPI + Uvicorn support for these commands.

## Polyfactory interoperability

- Automatic ModelFactory detection: when the `polyfactory` extra is installed, fixturegen scans discovered modules (and sibling `*.factories` packages) for `ModelFactory` subclasses and delegates matching models to them so nested relations, JSON samples, and pytest fixtures reuse the exact same logic without rewriting factories.
- Config toggles under `[polyfactory]` let you opt out (`prefer_delegation = false`) or point discovery at custom modules; logs highlight every delegate that gets wired in so you can audit migrations.
- `pfg gen polyfactory ./models.py --out factories.py` exports ready-to-import `ModelFactory` classes whose `.build()` methods call fixturegen under the hood, so teams can keep Polyfactory-centric APIs while benefiting from deterministic GenerationConfig settings.
- Seeds/locales stay in sync via the shared `SeedManager`: delegations reseed Polyfactory’s Faker + Random objects per path, keeping data parity between existing factories and fixturegen runs.

## Generation engine

- Depth-first instance builder with recursion limits and constraint awareness.
- Deterministic seeds cascade across Python `random`, Faker, and optional NumPy.
- NumPy array provider with configurable dtype/shape caps (enable the `numpy` extra).
- Numeric distribution controls (uniform, normal, spike) for ints/floats/decimals via the `[numbers]` configuration block or `PFG_NUMBERS__*` env vars.
- Configurable recursion handling with `max_depth` and `cycle_policy` (`reuse`, `stub`, `null`) so self-referential models keep realistic data; emitted JSON/fixtures annotate reused references via a `__cycles__` metadata block for easy review—even depth-limit fallbacks record exactly which policy fired and why.
- Portable SplitMix64 RNG core keeps seeds stable across Python versions/OSes, with `--rng-mode legacy` available for short-term migrations.
- Heuristic provider mapping that inspects field names, aliases, constraints, and `Annotated` markers to auto-select providers for emails, slugs, ISO country/language codes, filesystem paths, and more—every decision is surfaced in `pfg gen explain` with confidence scores.
- Relation-aware generation: declarative `relations` config / `--link` CLI flags reuse pools of generated models so foreign keys and shared references stay in sync, and JSON bundles can include related models via `--with-related`.
- Optional validator retries (`respect_validators` / `validator_max_retries`) that keep re-generation deterministic while surfacing structured diagnostics when model validators never converge.
- Field policies for enums, unions, and optional probabilities (`p_none`).
- Configuration precedence: CLI → environment (`PFG_*`) → pyproject/YAML → defaults.

## Hypothesis

- `pydantic_fixturegen.hypothesis.strategy_for(Model)` turns the generation metadata into shrinkable Hypothesis strategies that honour the same constraints, providers, and recursion policies as the fixture engine.
- `pfg gen strategies` emits a ready-to-import Python module that wires the discovered models into `strategy_for`, so property-based tests can share the exact same configuration (seed, cycle policy, RNG mode) as CLI/json workflows.
- Profiles (`typical`, `edge`, `adversarial`) bias the exporter toward larger boundary coverage when you need to stress validators or replicate adversarial scenarios.

## Emitters

- JSON/JSONL with optional `orjson`, sharding, and metadata banners.
- High-volume datasets via `pfg gen dataset` with streaming CSV writers and PyArrow-backed Parquet/Arrow sinks (install the `dataset` extra); cycle metadata is preserved in a `__cycles__` column for downstream QA.
- Pytest fixtures with deterministic parametrisation, configurable style/scope, and atomic writes.
- JSON Schema emission with sorted keys and trailing newline stability.

## Database seeding

- `pfg gen seed sqlmodel` connects to SQLite/Postgres URLs, batches fixturegen payloads into SQLModel/SQLAlchemy sessions, and supports schema creation, truncation, rollback-only runs, and dry-run logging. The allowlist guard ensures you explicitly opt into non-sqlite hosts with `--allow-url`.
- `pfg gen seed beanie` uses Motor to stream documents into MongoDB (or `mongomock_motor` for local tests); pass `--cleanup` to delete inserted documents at the end of each run so integration tests can re-use the same collections.
- Shared helpers in `pydantic_fixturegen.testing.seeders.SQLModelSeedRunner` turn any SQLModel engine and `ModelArtifactPlan` into a pytest fixture that seeds inside a transaction before every test.

## Deterministic anonymizer

- `pfg anonymize` ingests JSON/JSONL payloads (files or directory trees), applies rule-driven scrubbing (faker/hash/mask strategies), and mirrors the original layout when writing sanitized artifacts.
- Rule bundles live in TOML/YAML/JSON files and support glob/regex patterns, required flags, Faker providers, hash algorithm selection, and mask templates. Profiles such as `pii-safe` or `adversarial` pre-seed sensible rule sets and privacy budgets, and you can layer overrides with `--salt`, `--entity-field`, or `[anonymize.budget]` entries.
- Privacy budgets enforce deterministic redaction quality: if required rules never match or a strategy fails more than allowed, the CLI exits with a structured `EmitError`. `--report` writes a JSON summary containing before/after diff samples, per-strategy counts, and active thresholds so CI can archive evidence of each run.
- Doctor integration: pass `--doctor-target models.py` to pipeline sanitized data straight into `pfg doctor` gap detection; the resulting coverage snapshot is embedded in the report for auditing.
- Python API helpers (`anonymize_payloads`, `anonymize_from_rules`) expose the exact pipeline inside applications or bespoke scripts without shelling out to the CLI.

## Coverage lockfiles

- `pfg lock` captures a manifest of every model/field discovered (coverage counts, provider labels, gap summaries) and writes it to `.pfg-lock.json` so CI can diff coverage just like dependencies.
- `pfg verify` recomputes coverage and compares it against the lockfile, failing with a unified diff when coverage regresses or new fields appear without fresh fixtures/documentation.
- Manifests store the discovery options (module vs schema vs OpenAPI) so teams can enforce budgets consistently across services; combine with `--json-errors` for machine-readable CI logs.

## Plugins and extensibility

- Pluggy hooks: `pfg_register_providers`, `pfg_modify_strategy`, `pfg_emit_artifact`.
- Entry-point discovery for third-party packages.
- Strategy and provider registries open for customization via Python API or CLI.

## Security and sandboxing

- Safe-import sandbox blocking network access, jailing filesystem writes, and capping memory.
- Exit code `40` for timeouts, plus diagnostic events for violations.
- `pfg doctor` surfaces risky imports and coverage gaps.

## Profiles

- Built-in bundles exposed via `--profile` or `[tool.pydantic_fixturegen].profile`: `pii-safe`, `realistic`, `edge`, and `adversarial`.
- `pii-safe` masks identifiers with `example.com` emails, `example.invalid` URLs, reserved IP ranges, and deterministic test card numbers while nudging optional PII fields toward `None`.
- `realistic` restores richer Faker/identifier output and keeps optional contact fields populated for staging data.
- `edge` randomizes enum/union selection, increases optional `None` probabilities, and biases numeric sampling toward narrow spikes near min/max.
- `adversarial` further increases `p_none`, constrains collections to a handful of elements, and dials numeric spikes even tighter to stress downstream validators.
- Profiles compose with presets and explicit overrides, so you can layer additional field policies or configuration on top.

## Tooling quality

- Works on Linux, macOS, Windows for Python 3.10–3.14.
- Atomic IO for all emitters to prevent partial artifacts.
- Ruff, mypy, pytest coverage ≥90% enforced in CI.
- Optional watch mode (`[watch]` extra), JSON logging, and structured diagnostics for CI integration.

Dive deeper into specific areas via [configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md), [providers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md), [emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md), and [security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md).
