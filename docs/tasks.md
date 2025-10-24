# pydantic-fixturegen — Implementation Plan

A) Backlog

- [x] T-pydantic-fixturegen-product-spec-01: Repository bootstrap and package skeleton (60m)

  - Goal: Create `pyproject.toml`, base package `pydantic_fixturegen/`, and test scaffolding without functionality.
  - Files/paths: `pyproject.toml`, `pydantic_fixturegen/__init__.py`, `pydantic_fixturegen/cli/__init__.py`, `tests/`.
  - Key edits: Define project metadata, Python 3.10–3.13, extras stubs; create empty package modules.
  - Tests: Minimal sanity test `tests/test_imports.py` verifying package imports.
  - Dependencies: None.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-02: QA baseline (pytest, coverage, mypy strict, ruff) (60m)

  - Goal: Configure pytest, coverage thresholds, MyPy (strict), and Ruff/Black (via Ruff).
  - Files/paths: `pyproject.toml`, `tests/conftest.py`, `.github/workflows/ci.yml` (skeleton).
  - Key edits: Enable strict typing, set coverage ≥90% target, configure Ruff rules and Black profile.
  - Tests: Ensure CI runs `pytest -q`, `mypy`, and `ruff` successfully on empty skeleton.
  - Dependencies: T-01.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-03: CI workflow skeleton (tests + typecheck + lint) (45m)

  - Goal: Add GitHub Actions for matrix Python (3.10–3.13) to run lint, type-check, tests.
  - Files/paths: `.github/workflows/ci.yml`.
  - Key edits: Cache deps, run `pip install -e .[all-dev]` (or similar), enforce fail on warnings.
  - Tests: Green CI on main branch.
  - Dependencies: T-02.
  - Estimate: 45m.

- [x] T-pydantic-fixturegen-product-spec-04: Version metadata utility (tool_version + header helper) (30m)

  - Goal: Provide a function to get tool version and compose artifact headers.
  - Files/paths: `pydantic_fixturegen/core/version.py`, `tests/core/test_version.py`.
  - Key edits: Read version from package metadata; format header with seed/tool version/model digest.
  - Tests: Unit test header format and version retrieval.
  - Dependencies: T-01.
  - Estimate: 30m.

- [x] T-pydantic-fixturegen-product-spec-05: Deterministic seed plumbing (60m)

  - Goal: Implement `seed.py` to seed `random`, Faker, NumPy; expose deterministic streams.
  - Files/paths: `pydantic_fixturegen/core/seed.py`, `tests/core/test_seed.py`.
  - Key edits: Master seed → substreams keyed by (model, field, index); locale integration for Faker.
  - Tests: Repeatability across runs; independence across fields.
  - Dependencies: T-01.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-06: Config loader (pyproject/YAML/env) + precedence (90m)

  - Goal: Load config from `[tool.pydantic_fixturegen]`, YAML alternative, `PFG_*` env; merge with CLI.
  - Files/paths: `pydantic_fixturegen/core/config.py`, `tests/core/test_config.py`.
  - Key edits: Schema validation, precedence: CLI > env > config; defaults for seed/locale/policies.
  - Tests: Matrix tests for precedence and schema validation errors.
  - Dependencies: T-01, T-02.
  - Estimate: 90m.

- [x] T-pydantic-fixturegen-product-spec-07: Safe importer subprocess (sandbox env, time/mem caps) (90m)

  - Goal: Implement constrained import runner with `PYTHONSAFEPATH`, pruned `PYTHONPATH`, cwd jail, network block.
  - Files/paths: `pydantic_fixturegen/core/safe_import.py`, `tests/core/test_safe_import.py`.
  - Key edits: Spawn subprocess, enforce timeout/memory; serialize model list or errors.
  - Tests: Import side-effect module blocked from network; timeout triggers error code 40.
  - Dependencies: T-02.
  - Estimate: 90m.

- [x] T-pydantic-fixturegen-product-spec-08: AST discoverer for Pydantic models (75m)

  - Goal: Parse Python files to list `BaseModel`/`RootModel` classes without executing code.
  - Files/paths: `pydantic_fixturegen/core/ast_discover.py`, `tests/core/test_ast_discover.py`.
  - Key edits: Identify class bases, capture module/qualname; handle `__all__`, `--public-only`.
  - Tests: Detect models in a sample file; avoid executing module code.
  - Dependencies: T-02.
  - Estimate: 75m.

- [x] T-pydantic-fixturegen-product-spec-09: Discovery orchestration + include/exclude filters (60m)

  - Goal: Combine AST and import modes behind one API with include/exclude patterns.
  - Files/paths: `pydantic_fixturegen/core/introspect.py`, `tests/core/test_introspect.py`.
  - Key edits: Resolve forward refs/cycles later; return `DiscoveryResult`.
  - Tests: Filter by patterns; AST vs import parity on a sample module.
  - Dependencies: T-07, T-08.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-10: CLI `list` command (Typer) (45m)

  - Goal: Add `pfg list` with `--ast`, include/exclude, `--public-only`.
  - Files/paths: `pydantic_fixturegen/cli/__init__.py`, `pydantic_fixturegen/cli/list.py`, `tests/cli/test_list.py`.
  - Key edits: Wire to introspection; print models; support `--json-errors` on failure.
  - Tests: CLI invocation snapshot for both modes.
  - Dependencies: T-06, T-09.
  - Estimate: 45m.

- [x] T-pydantic-fixturegen-product-spec-11: Constraints extraction from Pydantic fields (75m)

  - Goal: Normalize Pydantic v2 field info to `FieldConstraints`.
  - Files/paths: `pydantic_fixturegen/core/schema.py`, `tests/core/test_schema_constraints.py`.
  - Key edits: Extract ge/le/gt/lt, min/max_length, pattern, min/max_items, unique_items, decimals.
  - Tests: Parametrized cases for constrained types.
  - Dependencies: T-01.
  - Estimate: 75m.

- [x] T-pydantic-fixturegen-product-spec-12: Support constrained types and standard extras (75m)

  - Goal: Handle `conint`, `constr`, `conlist`, `condecimal`, `EmailStr`, `IPvAny*`, `AnyUrl`, etc.
  - Files/paths: `pydantic_fixturegen/core/schema.py`, `tests/core/test_schema_extras.py`.
  - Key edits: Map to constraints; detect enum/literal/union/dataclasses.
  - Tests: Coverage for common constrained types and extras.
  - Dependencies: T-11.
  - Estimate: 75m.

- [x] T-pydantic-fixturegen-product-spec-13: Provider registry + pluggy hooks (60m)

  - Goal: Implement provider registry and `pfg_register_providers` hook.
  - Files/paths: `pydantic_fixturegen/core/providers.py`, `pydantic_fixturegen/plugins/hookspecs.py`, `tests/core/test_providers_registry.py`.
  - Key edits: Register core providers; resolve by type/constraints; load plugin entry points.
  - Tests: Register/unregister providers; plugin smoke test.
  - Dependencies: T-05, T-06.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-14: String and regex providers (with `[regex]`) (60m)

  - Goal: Implement `str` provider with Faker and optional regex via `rstr` extra.
  - Files/paths: `pydantic_fixturegen/core/providers/strings.py`, `tests/providers/test_strings.py`.
  - Key edits: Respect `max_length`, `pattern`; truncate/pad deterministically.
  - Tests: Regex pattern generation gated by extra; fallback warnings.
  - Dependencies: T-13.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-15: Numeric and Decimal providers (60m)

  - Goal: Implement `int`, `float`, `Decimal` providers honoring bounds/quantization.
  - Files/paths: `pydantic_fixturegen/core/providers/numbers.py`, `tests/providers/test_numbers.py`.
  - Key edits: Closed intervals for inclusive; epsilon/step for exclusive; Decimal quantize.
  - Tests: Bounds adherence, quantization.
  - Dependencies: T-13.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-16: Temporal and identifier providers (60m)

  - Goal: Implement `datetime`, `date`, `time` (zone-aware), `UUID`, URL/email/IPs/payment card.
  - Files/paths: `pydantic_fixturegen/core/providers/datetimes.py`, `tests/providers/test_datetimes.py`.
  - Key edits: Bounded windows; `zoneinfo`; Faker-backed identifiers.
  - Tests: TZ-aware outputs; bounds respected.
  - Dependencies: T-13.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-17: Collection providers (list/tuple/set/dict) (60m)

  - Goal: Implement min/max size and uniqueness; dict key/value mapping.
  - Files/paths: `pydantic_fixturegen/core/providers/collections.py`, `tests/providers/test_collections.py`.
  - Key edits: Enforce uniqueness when requested; stable ordering for determinism.
  - Tests: Size bounds and uniqueness invariants.
  - Dependencies: T-13, T-15.
  - Estimate: 60m.

- [x] T-pydantic-fixturegen-product-spec-18: Strategy builder and policies (90m)

  - Goal: Build `Strategy` per field from schema; apply defaults, `p_none`, union/enum policies.
  - Files/paths: `pydantic_fixturegen/core/strategies.py`, `tests/core/test_strategies.py`.
  - Key edits: Policy config, weighted unions, enum selection; overrides from config/CLI.
  - Tests: Matrix tests for policies and overrides.
  - Dependencies: T-11, T-12, T-13–T-17.
  - Estimate: 90m.

- [x] T-pydantic-fixturegen-product-spec-19: Recursive instance generator + guards (90m)

  - Goal: Generate model instances depth-first; enforce recursion depth and object budget.
  - Files/paths: `pydantic_fixturegen/core/generate.py`, `tests/core/test_generate.py`.
  - Key edits: Nested models/dataclasses; None fallback when limits exceeded.
  - Tests: Cycles and forward refs; referential density.
  - Dependencies: T-18.
  - Estimate: 90m.

- [x] T-pydantic-fixturegen-product-spec-20: JSON/JSONL emitter with sharding (75m)

  - Goal: Stream write JSON/JSONL; `--n`, `--jsonl`, `--indent 0|2`, `--orjson`; shard by `--shard-size`.
  - Files/paths: `pydantic_fixturegen/emitters/json_out.py`, `tests/emitters/test_json_out.py`.
  - Key edits: Worker pool for emission; partitioned filenames.
  - Tests: Shard sizes and line counts; orjson path when extra present.
  - Dependencies: T-19.
  - Estimate: 75m.

- [ ] T-pydantic-fixturegen-product-spec-21: Schema emitter (model_json_schema) (30m)

  - Goal: Export JSON schema for a model to file.
  - Files/paths: `pydantic_fixturegen/emitters/schema_out.py`, `tests/emitters/test_schema_out.py`.
  - Key edits: Call `model_json_schema()`; write atomically.
  - Tests: Schema content basic assertions; atomic write.
  - Dependencies: T-19.
  - Estimate: 30m.

- [ ] T-pydantic-fixturegen-product-spec-22: Atomic writes + content hashing utility (45m)

  - Goal: Prevent partial writes; skip when content unchanged.
  - Files/paths: `pydantic_fixturegen/core/io_utils.py`, `tests/core/test_io_utils.py`.
  - Key edits: Temp file + rename; optional hashing.
  - Tests: Idempotent writes; crash-safety.
  - Dependencies: T-01.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-23: Pytest fixture codegen (functions style) (90m)

  - Goal: Jinja template for function fixtures; imports de-duped; header metadata.
  - Files/paths: `pydantic_fixturegen/emitters/pytest_codegen.py`, `pydantic_fixturegen/templates/fixtures.j2`, `tests/emitters/test_pytest_codegen.py`.
  - Key edits: Render by seed; support `.model_dump()` when return_type=dict.
  - Tests: Snapshot tests for generated code; header includes seed/version/digest.
  - Dependencies: T-19, T-22.
  - Estimate: 90m.

- [ ] T-pydantic-fixturegen-product-spec-24: Fixture scopes/styles and formatting (60m)

  - Goal: Add factory/class styles, scopes (`function|module|session`), format via Ruff/Black.
  - Files/paths: `pydantic_fixturegen/emitters/pytest_codegen.py`, `pydantic_fixturegen/templates/factory_module.j2`, `tests/emitters/test_pytest_codegen_styles.py`.
  - Key edits: Import de-dup; formatting pipeline resilient to failure.
  - Tests: Style/scope variations; formatting applied.
  - Dependencies: T-23.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-25: CLI `gen json` command (60m)

  - Goal: Wire emitter to CLI with flags and config precedence.
  - Files/paths: `pydantic_fixturegen/cli/gen_json.py`, `tests/cli/test_gen_json.py`.
  - Key edits: Support `--n`, `--jsonl`, `--indent`, `--orjson`, `--shard-size`.
  - Tests: CLI E2E creating shards and samples.
  - Dependencies: T-20, T-06.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-26: CLI `gen schema` command (30m)

  - Goal: Wire schema emitter to CLI with `--out`.
  - Files/paths: `pydantic_fixturegen/cli/gen_schema.py`, `tests/cli/test_gen_schema.py`.
  - Key edits: Validate path; atomic write.
  - Tests: CLI schema output.
  - Dependencies: T-21, T-06.
  - Estimate: 30m.

- [ ] T-pydantic-fixturegen-product-spec-27: CLI `gen fixtures` command (75m)

  - Goal: Wire pytest codegen; flags: `--out`, `--style`, `--scope`, `--seed`, `--p-none`, `--cases`, `--return-type`.
  - Files/paths: `pydantic_fixturegen/cli/gen_fixtures.py`, `tests/cli/test_gen_fixtures.py`.
  - Key edits: Respect config precedence; idempotent output; format on write.
  - Tests: CLI E2E and snapshot for generated code.
  - Dependencies: T-24, T-06.
  - Estimate: 75m.

- [ ] T-pydantic-fixturegen-product-spec-28: Error taxonomy + JSON errors (60m)

  - Goal: Implement error codes 10/20/30/40 and `--json-errors` output.
  - Files/paths: `pydantic_fixturegen/core/errors.py`, `tests/core/test_errors.py`, adapt CLI.
  - Key edits: Map exceptions to codes; JSON schema for errors; surface in CLI.
  - Tests: Failure path assertions and snapshots.
  - Dependencies: T-10, T-25–T-27.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-29: Plugin hooks (providers, strategy, emitters) (75m)

  - Goal: Implement `pfg_modify_strategy` and `pfg_emit_artifact`; entry points for providers/emitters.
  - Files/paths: `pydantic_fixturegen/plugins/hookspecs.py`, `pydantic_fixturegen/plugins/loader.py`, `tests/plugins/test_hooks.py`.
  - Key edits: Define hookspecs; call order; error isolation.
  - Tests: Sample plugin exercises hooks.
  - Dependencies: T-13, T-18, T-23.
  - Estimate: 75m.

- [ ] T-pydantic-fixturegen-product-spec-30: Doctor command (coverage + risky imports) (75m)

  - Goal: Implement `pfg doctor` showing type coverage, unmapped constraints, risky imports.
  - Files/paths: `pydantic_fixturegen/cli/doctor.py`, `tests/cli/test_doctor.py`.
  - Key edits: Summaries and colored table; `--fail-on-warn`.
  - Tests: Flags and output snapshots.
  - Dependencies: T-09, T-18, T-28.
  - Estimate: 75m.

- [ ] T-pydantic-fixturegen-product-spec-31: `--explain` diagnostics (per-field strategies) (45m)

  - Goal: Add `--explain` to print chosen strategies/providers per field.
  - Files/paths: `pydantic_fixturegen/cli/common.py`, `tests/cli/test_explain.py`.
  - Key edits: Inspect strategies tree; pretty-print.
  - Tests: Snapshot `--explain` output.
  - Dependencies: T-18.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-32: Performance worker pool for JSON emission (60m)

  - Goal: Add worker pool; bound by CPU; measure throughput.
  - Files/paths: `pydantic_fixturegen/emitters/json_out.py`, `tests/perf/test_json_workers.py`.
  - Key edits: Parallelize encoding/writes safely; order-deterministic.
  - Tests: Speedup vs single-thread; correctness under determinism.
  - Dependencies: T-20.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-33: Memory budget and streaming safeguards (45m)

  - Goal: Ensure peak RSS ≤300MB for 10k medium objects.
  - Files/paths: `pydantic_fixturegen/emitters/json_out.py`, `tests/perf/test_memory_budget.py`.
  - Key edits: Batching; avoid accumulating large lists; backpressure.
  - Tests: Memory sampling and assertions (approximate).
  - Dependencies: T-20, T-32.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-34: Determinism integration test (60m)

  - Goal: Prove identical outputs across two runs with same inputs/seed/version.
  - Files/paths: `tests/e2e/test_determinism.py`.
  - Key edits: Golden files or byte comparison of outputs.
  - Tests: E2E against sample models.
  - Dependencies: T-19, T-20, T-23, T-27.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-35: CLI startup time optimization (45m)

  - Goal: Keep warm startup ≤200ms via lazy imports.
  - Files/paths: `pydantic_fixturegen/cli/__init__.py`, lazy import wrappers.
  - Key edits: Defer heavy deps (Faker, orjson) until used.
  - Tests: Startup timer smoke test.
  - Dependencies: T-10, T-25–T-27.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-36: Security hardening (network block + FS jail) (60m)

  - Goal: Strengthen safe-import sandbox and add tests.
  - Files/paths: `pydantic_fixturegen/core/safe_import.py`, `tests/security/test_sandbox.py`.
  - Key edits: Block `socket`, set `NO_PROXY=*`, restrict CWD writes; env scrub.
  - Tests: Attempts to open sockets or write outside target fail.
  - Dependencies: T-07.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-37: Packaging with Hatch + extras (45m)

  - Goal: Complete Hatch config, extras `[hypothesis]`, `[regex]`, `[orjson]`, `[all]`.
  - Files/paths: `pyproject.toml`.
  - Key edits: Build backends; classifiers; entry points for plugins/CLI.
  - Tests: `hatch build` succeeds locally.
  - Dependencies: T-01, T-29.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-38: Release pipeline and Trusted Publishing (60m)

  - Goal: GH Actions to build wheels/sdist, sign tags, and publish.
  - Files/paths: `.github/workflows/release.yml`.
  - Key edits: Matrix for OS/Python; PyPI Trusted Publishing.
  - Tests: Dry-run release.
  - Dependencies: T-37.
  - Estimate: 60m.

- [ ] T-pydantic-fixturegen-product-spec-39: Prebuilt GitHub Action wrapper (45m)

  - Goal: Provide `action.yml` to run `pfg` in CI.
  - Files/paths: `.github/actions/pfg/action.yml`, `README` snippet.
  - Key edits: Inputs: `module`, `out`, `seed`, `n`.
  - Tests: Local metadata check; example workflow.
  - Dependencies: T-25–T-27.
  - Estimate: 45m.

- [ ] T-pydantic-fixturegen-product-spec-40: Documentation — Quick start and cookbook (75m)
  - Goal: Author docs for installation, CLI usage, config, CI examples.
  - Files/paths: `docs/` (e.g., `docs/quickstart.md`, `docs/cookbook.md`).
  - Key edits: Examples for fixtures/JSON/schema; doctor; explain determinism.
  - Tests: Manual doc build; lint links.
  - Dependencies: T-25–T-27, T-30.
  - Estimate: 75m.

B) Milestones

- Milestone 1: Bootstrap & QA

  - Tasks: 01–04
  - Exit criteria: Package imports; CI green on empty skeleton; version utility works.

- Milestone 2: Config & Seed

  - Tasks: 05–06
  - Exit criteria: Deterministic RNG verified; config precedence tests passing.

- Milestone 3: Discovery (Safe-import + AST + list)

  - Tasks: 07–10
  - Exit criteria: `pfg list` supports AST/import with filters; sandbox enforced.

- Milestone 4: Schema & Constraints

  - Tasks: 11–12
  - Exit criteria: Constraints extraction covers core/constrained types.

- Milestone 5: Providers (core set)

  - Tasks: 13–17
  - Exit criteria: Providers for strings, numbers, temporal, identifiers, collections; registry pluggable.

- Milestone 6: Strategies & Policies

  - Tasks: 18
  - Exit criteria: Strategies produced with overrides and policies working.

- Milestone 7: Generator Engine

  - Tasks: 19
  - Exit criteria: Nested models generation with recursion/density guards.

- Milestone 8: Emitters (JSON/Schema)

  - Tasks: 20–22
  - Exit criteria: Streaming JSON/JSONL with sharding; schema export; atomic writes.

- Milestone 9: Pytest Codegen

  - Tasks: 23–24
  - Exit criteria: Fixtures generated in requested style/scope; formatted; idempotent.

- Milestone 10: CLI Integration & Errors

  - Tasks: 25–28
  - Exit criteria: `gen json`, `gen schema`, `gen fixtures` usable with error taxonomy.

- Milestone 11: Plugins & Extensibility

  - Tasks: 29
  - Exit criteria: Pluggy hooks available; sample plugin works.

- Milestone 12: Diagnostics & Doctor

  - Tasks: 30–31
  - Exit criteria: `pfg doctor` reports coverage/unmapped; `--explain` works.

- Milestone 13: Performance & Determinism

  - Tasks: 32–35
  - Exit criteria: 10k medium ≤5s, ≤300MB; repeatability proven; startup ≤200ms.

- Milestone 14: Security, Packaging, Release, Docs
  - Tasks: 36–40
  - Exit criteria: Sandbox hardened; build/publish pipelines ready; docs published; GitHub Action wrapper available.

C) AC Checklist

- AC-pydantic-fixturegen-product-spec-01: List models via AST without import — Verifier: Dev + Reviewer

  - [ ] `pfg list <file> --ast` exits 0 and lists models without executing module code.

- AC-pydantic-fixturegen-product-spec-02: Generate fixtures deterministically — Verifier: Dev + CI

  - [ ] `pfg gen fixtures` produces fixtures for a model; rerun yields identical file.

- AC-pydantic-fixturegen-product-spec-03: Respect defaults unless ignored — Verifier: Dev

  - [ ] Defaulted fields equal defaults; `--ignore-defaults` changes values unless `p_none` applies.

- AC-pydantic-fixturegen-product-spec-04: JSONL generation with sharding — Verifier: Dev + CI

  - [ ] `--n 10000 --jsonl --shard-size 2000` writes 5 shards of 2000 lines.

- AC-pydantic-fixturegen-product-spec-05: Deterministic seed across runs — Verifier: CI

  - [ ] Two runs with same inputs/seed/version are byte-identical.

- AC-pydantic-fixturegen-product-spec-06: Enforce numeric constraints — Verifier: Dev

  - [ ] Values satisfy `ge/le/gt/lt`; Decimal quantized to `decimal_places` with `max_digits`.

- AC-pydantic-fixturegen-product-spec-07: Safe import mode in CI — Verifier: Dev + Security reviewer

  - [ ] Import runs in constrained subprocess; outbound network blocked.

- AC-pydantic-fixturegen-product-spec-08: Policies for Union and Enum — Verifier: Dev

  - [ ] `union_policy=first|random|weighted` and `enum_policy=first|random` respected deterministically.

- AC-pydantic-fixturegen-product-spec-09: Config precedence — Verifier: Dev

  - [ ] CLI > env > config precedence enforced during generation.

- AC-pydantic-fixturegen-product-spec-10: Error codes and JSON errors — Verifier: Dev + Reviewer

  - [ ] Exit codes 10/20/30/40; `--json-errors` prints machine-readable payloads.

- AC-pydantic-fixturegen-product-spec-11: Schema export — Verifier: Dev

  - [ ] `pfg gen schema` writes `model_json_schema()` output to file.

- AC-pydantic-fixturegen-product-spec-12: Doctor reports coverage — Verifier: Dev
  - [ ] `pfg doctor` lists unmapped fields/constraints and risky imports.

D) Context Digest

- docs/specs/pydantic-fixturegen-product-spec/requirements.md:1 — Source of approved requirements and ACs.
- docs/specs/pydantic-fixturegen-product-spec/design.md:1 — Detailed technical design and architecture.
- docs/specs/pydantic-fixturegen-product-spec/description.md:1 — Product narrative and reference.

Ready to implement

- Approve: `docs/specs/pydantic-fixturegen-product-spec/requirements.md`, `docs/specs/pydantic-fixturegen-product-spec/design.md`, `docs/specs/pydantic-fixturegen-product-spec/tasks.md`.
