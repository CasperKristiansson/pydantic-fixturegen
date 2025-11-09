# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added schema ingestion workflows: `pfg gen json --schema` ingests standalone JSON Schema files, `pfg gen openapi` fans out OpenAPI 3.x routes into per-schema JSON samples, and `pfg doctor --schema/--openapi` surfaces coverage gaps without writing Python models; documents are cached under `.pfg-cache/schemas`, and the new `openapi` extra bundles `datamodel-code-generator` + PyYAML for these commands (addresses issue #36).
- Added high-volume dataset emitters (issue #39): `pfg gen dataset` streams CSV files and writes PyArrow-backed Parquet/Arrow sinks with sharding, cycle metadata, and the same deterministic seeds/presets as `gen json`; install the new `dataset` extra (PyArrow) to enable columnar formats.
- Introduced a deterministic anonymizer (issue #41): `pfg anonymize` ingests JSON/JSONL payloads, rewrites sensitive fields via rule sets (faker/hash/mask strategies), enforces privacy budgets with salt rotation/entity-key controls, emits before/after diff reports, exposes a Python helper (`anonymize_payloads` / `anonymize_from_rules`), and can feed results into `pfg doctor` for gap analysis.
- Added coverage lockfiles (issue #42): `pfg lock` records a machine-readable manifest of model coverage/provider usage, while `pfg verify` recomputes the manifest and fails CI when coverage regresses; manifests capture discovery options, per-field providers, and gap summaries so teams can enforce budgets via simple diffable artifacts.
- Expanded snapshot tooling (issue #44): new CLI helpers `pfg snapshot verify`/`pfg snapshot write` wrap the snapshot runner for CI-friendly drift checks, the pytest plugin now respects `pytest-regressions` flags (`--force-regen`/`--regen-all`) without custom glue, and `pfg diff`/snapshot failures include hint lines that explain *why* artifacts changed (schema definition churn, fixture header deltas, added/removed JSON fields, constraint hints).
- Published comparative docs & migration guides (issue #48): refreshed `docs/alternatives.md` with a feature-by-feature matrix, Polyfactory/Pydantic-Factories migration playbooks, and real case studies; reorganised the docs index + quickstart to highlight benefits/next steps; expanded the CLI/API references (new command map, `pfg snapshot`, FastAPI, dataset/anonymizer coverage) so every parameter is documented before readers dive in.
- Delivered ORM seeders - `pfg gen seed sqlmodel` wraps SQLModel/SQLAlchemy inserts in transactions (with schema creation, truncation, rollback-only, and dry-run modes), `pfg gen seed beanie` streams documents into MongoDB with optional cleanup, and the new `[sqlmodel]`, `[beanie]`, and `[seed]` extras make these integrations one-command installs.
- Introduced FastAPI tooling (issue #37): `pfg fastapi smoke` scaffolds pytest smoke tests per route, `pfg fastapi serve` launches a deterministic mock server with dependency overrides, and the new `pfg gen examples` command injects fixture-derived example payloads into OpenAPI documents. Enable the `fastapi` extra to pull in FastAPI/Uvicorn support.
- Added Polyfactory interoperability (issue #38): installing the new `polyfactory` extra lets fixturegen auto-detect `ModelFactory` subclasses on the discovery path (or in `[polyfactory].modules`), delegate matching models to those factories during `gen json`/`gen fixtures`/FastAPI runs, and export wrapper factories via `pfg gen polyfactory` for teams that want to keep Polyfactory-facing APIs while reusing `GenerationConfig` settings.
- Added cross-platform filesystem path providers for `pathlib.Path`, `pydantic.DirectoryPath`, and `pydantic.FilePath` fields, including a new `[paths]` configuration section for default OS targets and per-model overrides that flow through the CLI, Python API, and emitters.
- Added configurable deterministic identifier providers for emails, URLs, UUIDs, secrets, and payment cards; provider behaviour is governed by new `[identifiers]` settings in project config.
- Added a heuristic provider mapping engine that inspects field names, aliases, constraints, and `Annotated` metadata to automatically route common shapes (emails, slugs, currency codes, ISO country/language identifiers, filesystem paths, etc.) onto richer providers, complete with explain provenance in `pfg gen explain`, a `[heuristics]` opt-out switch, and a new `pfg_register_heuristics` pluggy hook for custom rules.
- Added a built-in slug provider (also used for `SlugStr` annotations) to keep URL-friendly tokens deterministic and honor length constraints.
- Added recursion-aware generation with configurable `max_depth`/`cycle_policy` settings plus `--max-depth`/`--on-cycle` CLI overrides; recursive fields now reuse prior instances, emit stubs, or fall back to null deterministically, and JSON/fixture emitters surface the behaviour via a `__cycles__` metadata block while `pfg gen explain` shows the active policy per field.
- Added a portable SplitMix64 RNG core that keeps seeded runs byte-for-byte identical across Python versions and operating systems, along with a new `rng_mode` configuration key and `--rng-mode {portable,legacy}` CLI/ENV overrides for teams that need to temporarily fall back to the legacy CPython RNG.
- Added adversarial generation profiles (`edge`, `adversarial`) that bias datasets toward boundary conditions—spiky numeric sampling, higher optional `None` rates, and smaller collections—accessible via `profile = "edge"`/`"adversarial"` or `--profile`.
- Added a Hypothesis strategy exporter: `pydantic_fixturegen.hypothesis.strategy_for(Model)` converts model metadata into shrinkable strategies, and `pfg gen strategies` writes ready-to-import modules wired to the same seed/rng-mode/cycle-policy options for property-based tests.
- Made email and payment identifier dependencies optional extras (`[email]`, `[payment]`), so base installations no longer require `email-validator` or `pydantic-extra-types`, and the docs now call out the opt-in requirements explicitly.
- Established tested minimum dependency floors on Python 3.10 and 3.14: `faker>=3.0.0`, `pydantic>=2.12.4`, `typer>=0.12.4,<0.13`, `click>=8.1.7,<8.2`, `pluggy>=1.5.0`, and `tomli>=2.0.1` (for Python 3.10 only). Optional extras now document the verified baselines: `email-validator>=2.0.0`, `pydantic-extra-types>=2.6.0`, `rstr>=3.2.2`, `orjson>=3.11.1`, `hypothesis>=1.0.0`, `numpy>=2.2.6` on Python 3.10 / `>=2.3.2` on Python ≥3.11`, and `watchfiles>=0.20.0`.
- Added `pfg plugin new` to scaffold pluggy provider projects with packaging metadata, tests, and CI workflow templates.
- Added VS Code workspace tasks and JSON problem matcher to run `pfg` commands with inline diagnostics.
- Added a pytest snapshot helper (`pfg_snapshot`) with update modes for JSON, fixture, and schema artifacts.
- Added `@pytest.mark.pfg_snapshot_config(...)` so individual pytest tests can override the snapshot fixture's update mode and sandbox controls without affecting the rest of the suite.
- Added per-model/field Faker locale mapping with validation and runtime overrides.
- Locale override patterns now match bare model names (with or without module prefixes), so specifying `app.models.User` or `User` applies to every field without writing `.*`.
- Added privacy profiles (`pii-safe`, `realistic`) selectable via `--profile`/`PFG_PROFILE`/`[tool.pydantic_fixturegen].profile` to mask identifiers or favour realistic datasets.
- Added numeric distribution controls (`[numbers]` config) enabling uniform, normal, or bounded spike sampling for ints/floats/decimals.
- Added deterministic NumPy array providers with configurable shape/dtype caps (requires the `numpy` extra).
- Added validator-aware retries controlled by `respect_validators`/`validator_max_retries`, exposing matching CLI flags on `gen json`, `gen fixtures`, and `diff` plus structured `validator_failure` diagnostics when retries exhaust.
- Added relation-aware generation via `[relations]` config and new `--link` / `--with-related` CLI flags so JSON bundles and pytest fixtures can keep foreign keys aligned across models while emitting related records together; diff now understands the relation overrides too.
- Added automatic providers for a broad set of `pydantic-extra-types` annotations (colors, coordinates, phone numbers, cron strings, semantic versions, ULIDs, etc.) with matching `pfg doctor` diagnostics when the optional dependency is missing so gaps are surfaced early.
- Added TypeAdapter generation to `pfg gen json`/`generate_json` via `--type`/`type_annotation`, including CLI expression evaluation, watch safeguards, and detailed MappingError diagnostics when adapter validation fails.

### Fixed

- Cycle metadata is now attached to generated models even when recursion is limited solely by `max_depth`, ensuring `__cycles__` blocks in JSON and pytest fixtures always report the active `cycle_policy` (addresses issue #33).
- Deterministic seed freezing, explain/doctor reports, heuristics, and pytest fixture emitters now normalize models back to their canonical `module.Class` identifiers even when the same file is imported multiple times under internal aliases, keeping `.pfg-seeds.json`, CLI output, and generated imports stable after running other commands (fixes issue #35).

## [1.1.0] - 2025-11-04

### Added

- Introduced `pfg init` to scaffold recommended configuration (pyproject or YAML) and create fixture directories with atomic writes.
- Added `pfg check` for dry-run validation of configuration, discovery, and emitter destinations.
- Added `pfg diff` to regenerate artifacts in a sandbox and highlight drift across JSON, fixtures, and schema outputs.
- Published an authoritative configuration JSON Schema (`pfg schema config`, bundled at `pydantic_fixturegen/schemas/config.schema.json`).
- Added watch mode (`--watch`) to generation commands for automatic regeneration on file changes (requires the optional `watch` extra).
- Introduced structured logging controls (`-v/-q` verbosity tiers and `--log-json` for machine-readable events with stable `event` + `context` fields).
- Introduced boundary coverage presets (`--preset` with `boundary` / `boundary-max`) that tune union/enum policies and optional `None` probabilities for edge-case heavy datasets.
- Added constraint reporting across generation and diff commands, surfacing unmet model constraints with actionable hints in both human-readable and structured outputs.
- Added deterministic seed freeze support (`--freeze-seeds`, `.pfg-seeds.json`) with per-model digests, warnings for stale data, and CLI integration across generation/diff commands.
- Added `--now` option to JSON/fixture/diff workflows to pin temporal data to a reproducible anchor timestamp and surface the chosen value in artifact metadata.
- `--out` destinations for JSON, schema, and fixture commands now support templated paths with `{model}`, `{case_index}`, and `{timestamp}` placeholders, normalised to safe segments.
- Added public Python helpers (`pydantic_fixturegen.api`) exposing `generate_json`, `generate_fixtures`, and `generate_schema` with typed result objects.
- Field policies now support glob or regex patterns targeting model names, nested field paths (for example `User.address.city`), and plain field names in addition to fully-qualified module paths.
- `pfg doctor` now enumerates unsupported type coverage, aggregates remediation guidance, and supports `--fail-on-gaps` to raise CI-friendly exit codes when uncovered fields remain.
- JSON, schema, and fixture emitters now enforce canonical key ordering and trailing newline policy for deterministic artifacts.
- Enhanced `pfg gen explain` with a structured `--json` payload, ASCII `--tree` visualization, and `--max-depth` controls for nested strategy exploration.
- Major documentation overhaul: README trimmed to a quick-start landing page, deep content moved into dedicated `/docs` guides, added cookbook alias, and expanded sections for configuration, CLI usage, presets, seeds, security, and troubleshooting.

### Fixed

- Resolved safe-import sandbox failures for modules that rely on package-relative imports, ensuring `pfg list` and related commands discover models inside packages.

### Tests

- Added regression coverage for relative import discovery, the new CLI scaffolding workflow, and artifact diff validation across JSON and fixtures.
- Expanded tests for existing CLI functionality, covering diff error handling, check validations, init scaffolding branches, and watch mode fallbacks.

## [1.0.0] - 2025-10-24

### Added

- Deterministic generation for Pydantic v2 models with cascading seeds across `random`, Faker, and optional NumPy providers.
- Secure safe-import sandbox that locks down networking, constrains resources, and jails filesystem writes when discovering models.
- CLI toolchain with discovery and generation commands: `pfg list`, `pfg gen json`, `pfg gen fixtures`, `pfg gen schema`, `pfg gen explain`, and `pfg doctor`.
- Emitters for JSON/JSONL artifacts, pytest fixture modules, and JSON Schema files with atomic writes and reproducibility metadata.
- Pluggable data provider system built on Pluggy with built-in strategies for collections, temporal values, identifiers, and regex-driven strings.
- Configuration precedence across CLI arguments, `PFG_*` environment variables, and `pyproject.toml`/YAML settings for reproducible runs.
- Quality toolchain with Ruff, MyPy, and pytest across Python 3.10–3.13 and a release pipeline using Hatch builds and PyPI trusted publishing.
