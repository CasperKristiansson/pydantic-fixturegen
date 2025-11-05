# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `pfg plugin new` to scaffold pluggy provider projects with packaging metadata, tests, and CI workflow templates.
- Added VS Code workspace tasks and JSON problem matcher to run `pfg` commands with inline diagnostics.
- Added a pytest snapshot helper (`pfg_snapshot`) with update modes for JSON, fixture, and schema artifacts.

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
