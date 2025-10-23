# pydantic-fixturegen — Product Spec

## 1. Summary

- Goal: Generate deterministic fake data from Pydantic v2 models and emit usable artifacts (pytest fixtures and JSON/JSONL samples) via a safe, reproducible CLI and extensible codegen.
- Why: Replace slow, flaky, and hand-written factories with model-aware, deterministic generation to speed up CI, harden contract tests, and reduce boilerplate.
- How: Discover models safely, synthesize field strategies from types and constraints, generate instances deterministically, and emit artifacts (code, JSON, schema) with strong DX and CI integration.

## 2. Business Context and Goals

- Teams with Pydantic v2 models lack fast, deterministic test data that stays in sync with models.
- Existing tools either require custom factories or work from JSON Schema instead of Pydantic models.
- Provide a single command to produce repeatable fixtures and JSON samples, safe to run in CI, with extensibility points for providers and emitters.

Success metrics
- Time to first fixture ≤ 2 minutes for a new project.
- Replace ≥ 80% of hand-written factories in target repos.
- CI time reduction on data generation steps.
- Adoption indicators: GitHub stars, PyPI downloads, external issues.

## 3. In Scope and Out of Scope

In scope
- CLI commands: `list`, `gen fixtures`, `gen json`, `gen schema`, `doctor`.
- Safe model discovery (import/AST modes) with include/exclude controls.
- Deterministic instance generation with constraints and provider mapping for core types.
- Emitters for pytest fixtures, JSON/JSONL, and schema export.
- Config via `pyproject.toml`, YAML alternative, and env vars with `PFG_` prefix.
- Plugin mechanism (providers, strategy modifiers, emitters) via Pluggy + entry points.
- CI-friendly behavior (safe import, reproducibility, formatting, error codes, JSON errors).

Out of scope (v1)
- ORM object creation for Django/SQLAlchemy.
- Networked data generation.
- Mutation testing or fuzzing beyond optional Hypothesis integration.

## 4. Users and Use Cases

Users
- Backend engineers: generate fixtures for unit and API tests.
- QA/contract testers: produce JSON examples to pin contracts and seed mock servers.
- Data/ML engineers: create representative payloads for pipelines and validation.
- OSS maintainers: publish example payloads in docs.

Primary use cases
- Generate pytest fixtures into `tests/conftest.py` or module-specific files.
- Emit large JSON/JSONL samples with sharding for load tests and mocks.
- Export Pydantic schemas to verify and document contract surfaces.
- Audit models for unmapped fields/constraints and unsafe imports via `doctor`.

## 5. Functional Requirements

5.1 Model discovery
- Inputs accept: module path (`pkg.models`), file path (`src/pkg/models.py`), or explicit `path.to:Model`.
- Enumerate subclasses of `pydantic.BaseModel` and `pydantic.RootModel`.
- Modes:
  - Import mode (default): import in a constrained subprocess with safe-import controls.
  - AST mode: parse Python files to list candidate model classes without executing module code; import by name only if selected.
- Filtering: include/exclude patterns (glob), `--public-only` to prefer non-underscore names.
- Resolve forward refs and circular dependencies.

5.2 Generation core
- Build a per-field Strategy using type info and Pydantic metadata: `Annotated`, `Field(ge, le, gt, lt, min_length, max_length, pattern, min_items, max_items, unique_items)`, constrained types (e.g., `conint`, `constr`, `conlist`, `condecimal`), standard extras (`EmailStr`, `IPvAnyAddress`, `PaymentCardNumber`, `Color`, etc.).
- Handle `Union`, `Optional`, `Literal`, `Enum`, nested models, dataclasses.
- Defaults respected; `--ignore-defaults` forces fake values instead of defaults.
- `None` probability (`p_none`) configurable globally and per field; default 0.1.
- Determinism: single seed drives Python `random`, Faker, and NumPy (if present); stable output for identical inputs, seed, and tool version.
- Performance: streaming generation with chunked writes; worker pool for JSON emission.

5.3 Type → provider mapping (core set)
- `str`: Faker text truncated to `max_length`; regex generation via optional `[regex]` extra.
- `int`/`float`: respect numeric bounds; `Decimal` quantized to `decimal_places` with `max_digits`.
- `bool`: random boolean.
- `datetime`/`date`/`time`: bounded windows; timezone-aware with `zoneinfo`.
- `UUID`: v4; URLs, emails, IPs, payment card numbers, color via Faker providers.
- `list`/`tuple`/`set`: size within `[min_items, max_items]`, uniqueness enforced if requested.
- `dict`: keys from provider, values from mapped strategy.
- `SecretStr`/`SecretBytes`: Faker password or bytes.
- Fallback: raise actionable error unless `--allow-fallback` uses placeholder sentinel values.

5.4 Overrides and policies
- Per-model/field overrides via config and CLI: fixed values, custom provider, range tweaks.
- Union selection policy: `first|random|weighted` (+ weights).
- Enum/Literal policy: `first|random`.
- Referential density: configurable recursion depth and object graph size limits.

5.5 Emitters
- Pytest fixtures (codegen)
  - Output target: `tests/conftest.py` or a module file.
  - Styles: function fixtures, factory functions, or class-based factory.
  - Scopes: `function|module|session`.
  - Return type: `Model` instance or `dict` via `.model_dump()`.
  - Parametrized fixtures with `--cases N`.
  - Imports deduped; formatted with Black (via Ruff) on emit; type hints for MyPy/Pyright.
  - Header comment with seed, tool version, and model digest.
- JSON/JSONL samples
  - Flags: `--n`, `--jsonl`, `--indent 0|2`, `--orjson`.
  - Partitioned output with `--shard-size`.
  - Schema export using `model_json_schema()`.
- Hypothesis (optional)
  - Emit strategies for models (e.g., `st.builds(Model, ...)`) gated behind `[hypothesis]` extra.

5.6 CLI
```
pfg list <module-or-file> [--ast] [--include ...] [--exclude ...]
pfg gen fixtures <module-or-model> --out tests/conftest.py --style functions --scope function --seed 42 --p-none 0.1
pfg gen json <module-or-model> --n 1000 --out samples/Model.jsonl --jsonl --seed 42 --indent 0
pfg gen schema <module-or-model> --out schema/Model.json
pfg doctor <module-or-file>  # report unmapped fields, cycles, risky imports
```
- Global flags: `--safe-import`, `--workers`, `--locale`, `--verbose`, `--dry-run`, `--fail-on-warn`.

5.7 Configuration
- Primary: `pyproject.toml` under `[tool.pydantic_fixturegen]`.
- Keys: `seed`, `locale`, `include`, `exclude`, `p_none`, `union_policy`, `enum_policy`, `overrides.{Model}.{field}`, `emitters.pytest.style`, `emitters.pytest.scope`, `json.indent`, `json.orjson`.
- YAML config supported as an alternative.
- Env var prefix `PFG_` mirrors keys; precedence CLl > env > config.

5.8 Plugins and extensibility
- Pluggy hook specs:
  - `pfg_register_providers(registry)`
  - `pfg_modify_strategy(model, field, strategy)`
  - `pfg_emit_artifact(kind, ctx)`
- Entry points:
  - `pydantic_fixturegen.providers`
  - `pydantic_fixturegen.emitters`
- Extras: `[django]`, `[sqlalchemy]`, `[hypothesis]`, `[regex]`, `[orjson]`.

5.9 Safety
- Default safe import mode (true in CI): forked subprocess with constrained environment: `PYTHONSAFEPATH`, empty `PYTHONPATH` except project, cwd jail, `NO_PROXY=*`, network blocked, time and memory caps.
- AST listing to avoid executing module code during discovery.
- No telemetry. No outbound network.

5.10 Logging and DX
- Rich console with levels; `--verbose` controls.
- `pfg doctor` prints coverage table per type and flags unmapped constraints.
- `--explain` dumps chosen strategy per field.

5.11 Errors
- Clear exit codes: `10` discovery error, `20` mapping error, `30` emit error, `40` unsafe import violation.
- Machine-readable `--json-errors` mode for CI parsing.

## 6. Acceptance Criteria (Gherkin)

Note: `<slug>` = `pydantic-fixturegen-product-spec`.

Scenario: AC-pydantic-fixturegen-product-spec-01 List models via AST without import
  Given a Python file path containing Pydantic v2 models
  When I run `pfg list <file> --ast`
  Then the command exits with code 0
  And it prints detected model names without importing module code

Scenario: AC-pydantic-fixturegen-product-spec-02 Generate fixtures deterministically
  Given a module path with a `User` Pydantic model
  When I run `pfg gen fixtures <module> --out tests/conftest.py --seed 42`
  Then the command exits with code 0
  And `tests/conftest.py` contains a fixture for `User`
  And rerunning the same command produces an identical file

Scenario: AC-pydantic-fixturegen-product-spec-03 Respect defaults unless ignored
  Given a model field with a default value
  When I generate fixtures without `--ignore-defaults`
  Then the generated value equals the default
  When I generate fixtures with `--ignore-defaults`
  Then the generated value differs from the default unless `p_none` triggers None

Scenario: AC-pydantic-fixturegen-product-spec-04 JSONL generation with sharding
  Given a model and `--n 10000 --jsonl --shard-size 2000`
  When I run `pfg gen json <model> --out samples/Model.jsonl`
  Then the command exits with code 0
  And it writes 5 shard files each containing 2000 JSONL lines

Scenario: AC-pydantic-fixturegen-product-spec-05 Deterministic seed across runs
  Given identical inputs, seed, and tool version
  When I generate 100 objects twice
  Then the two outputs are byte-identical

Scenario: AC-pydantic-fixturegen-product-spec-06 Enforce numeric constraints
  Given a model with `Field(ge=1, le=10)` and `condecimal(max_digits=5, decimal_places=2)`
  When I generate JSON samples
  Then all numeric values satisfy the configured bounds and quantization

Scenario: AC-pydantic-fixturegen-product-spec-07 Safe import mode in CI
  Given a module with import side effects
  When I run with `--safe-import` (default in CI)
  Then module import occurs in a constrained subprocess
  And outbound network access is blocked

Scenario: AC-pydantic-fixturegen-product-spec-08 Policy controls for Union and Enum
  Given a field of type `Union[A, B]` and an `Enum`
  When union policy is `first`
  Then generated values always use the first union member
  When enum policy is `random`
  Then values are drawn from the enumeration with a deterministic RNG

Scenario: AC-pydantic-fixturegen-product-spec-09 Config precedence
  Given values specified in `pyproject.toml`, env vars, and CLI flags
  When generating fixtures
  Then CLI flags override env vars, which override config file values

Scenario: AC-pydantic-fixturegen-product-spec-10 Error codes and JSON errors
  Given an unmapped constrained type without fallback allowed
  When I run generation
  Then the process exits with code 20
  And `--json-errors` prints a machine-readable error object

Scenario: AC-pydantic-fixturegen-product-spec-11 Schema export
  Given a Pydantic model
  When I run `pfg gen schema <model> --out schema/Model.json`
  Then the command exits with code 0
  And the file contains `model_json_schema()` output

Scenario: AC-pydantic-fixturegen-product-spec-12 Doctor reports coverage
  Given a module with constrained fields and an unknown type
  When I run `pfg doctor <module>`
  Then the command exits with code 0
  And it lists unmapped fields/constraints and possible remedies

## 7. Non-functional Requirements

Performance
- Generate 10k JSON objects for a medium model (≈20 fields, 3 nested) in ≤ 5 seconds on a laptop CPU.
- Peak RSS ≤ 300 MB during generation of 10k objects.
- CLI warm startup time ≤ 200 ms.

Determinism
- Identical outputs across two runs on the same platform and tool version given identical inputs and seed.
- Embed metadata (seed, tool version, model digest) into emitted artifacts.

Portability
- Supported Python versions: 3.10–3.13.
- Operating systems: Linux, macOS, Windows.

Security and Privacy
- No telemetry; no outbound network usage during discovery/generation.
- Safe import sandbox by default in CI; memory and time limits.
- AST discovery that avoids executing untrusted code.
- Generated data is synthetic/fake; avoid emitting real PII.

Availability and Cost
- Pure-Python wheels; fast local generation without external services.
- Optional extras to tune dependency footprint (e.g., `[orjson]`).

Quality
- Test coverage ≥ 90% lines; Hypothesis for invariants where practical.
- Type checking: MyPy strict passes without errors.

## 8. Compliance and Regulatory

- No specific regulatory requirements identified.
- Privacy: Ensure generated examples do not inadvertently incorporate real user data.
- Licensing: Ensure bundled providers/templates are compatible with project license.

## 9. Risks and Mitigations

- Pydantic version drift: Pin tested versions and maintain adapters.
- Regex generation complexity: Keep `[regex]` optional with clear fallbacks and warnings.
- Import side effects: Default safe mode and AST discovery minimize execution of untrusted code.
- Cross-platform determinism: Document OS/Python caveats; embed metadata for traceability.

## 10. Assumptions and Dependencies

Assumptions
- Project will use Typer for CLI, Rich for console, Pluggy for plugins, Faker for providers, Ruff/Black for formatting, Hatch for packaging, optional orjson for speed.
- CI will run safe-import mode by default.

Dependencies
- Runtime: `pydantic>=2`, `faker`, `pluggy`, optional `orjson`, `rstr` (for `[regex]`), `hypothesis` (optional), `numpy` (optional), `rich`, `typer`.
- Dev: `ruff`, `black` (via Ruff), `mypy` (strict), `pytest`, `hatch`.

## 11. Open Questions

- Should AST discovery support multi-file package analysis without importing `__init__` modules?
- How to configure deterministic ranges for time-based fields across time zones?
- What is the default shard file naming scheme and rotation policy?
- How to expose per-field `p_none` overrides on the CLI ergonomically?
- Do we support `BaseModel` `computed_field` and `field_serializer` semantics during generation, or always rely on model validation?
- Should plugin hooks allow vetoing model emission, and if so, how are conflicts resolved?

## 12. Context Digest (Repository Scan)

Note: Workspace appears empty; no context files discovered. Assumptions above are based on the provided product spec.

- . : empty repository; no `README*`, `pyproject.toml`, or source files found

