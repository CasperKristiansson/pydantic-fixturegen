# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2025-10-25

### Added

- Introduced `pfg init` to scaffold recommended configuration (pyproject or YAML) and create fixture directories with atomic writes.

### Fixed

- Resolved safe-import sandbox failures for modules that rely on package-relative imports, ensuring `pfg list` and related commands discover models inside packages.

### Tests

- Added regression coverage for relative import discovery and the new CLI scaffolding workflow.

## [1.0.0] - 2025-10-24

### Added

- Deterministic generation for Pydantic v2 models with cascading seeds across `random`, Faker, and optional NumPy providers.
- Secure safe-import sandbox that locks down networking, constrains resources, and jails filesystem writes when discovering models.
- CLI toolchain with discovery and generation commands: `pfg list`, `pfg gen json`, `pfg gen fixtures`, `pfg gen schema`, `pfg gen explain`, and `pfg doctor`.
- Emitters for JSON/JSONL artifacts, pytest fixture modules, and JSON Schema files with atomic writes and reproducibility metadata.
- Pluggable data provider system built on Pluggy with built-in strategies for collections, temporal values, identifiers, and regex-driven strings.
- Configuration precedence across CLI arguments, `PFG_*` environment variables, and `pyproject.toml`/YAML settings for reproducible runs.
- Quality toolchain with Ruff, MyPy, and pytest across Python 3.10–3.13 and a release pipeline using Hatch builds and PyPI trusted publishing.
