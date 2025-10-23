# pydantic-fixturegen — Product Spec

## Executive summary

Generate deterministic fake data from Pydantic v2 models and emit usable artifacts: pytest fixtures and JSON/JSONL samples. Fill the gap between model-aware factories and ready-to-run tests by adding a CLI and codegen with strict reproducibility and safe model discovery.

## Problem

- Teams have Pydantic models but lack fast, deterministic test data. Manual factories slow CI and drift from models.
- Existing generators either require handwritten factories or target JSON Schema, not models.
- No widely adopted tool emits pytest fixture code and JSON samples from Pydantic v2 with a simple CLI.
  **Impact:** Slower onboarding, flaky tests, duplicated boilerplate, weak contract tests.

## Goals

- One command to generate fixtures and JSON from models with a fixed seed.
- Zero hand-written factories for common types and constraints.
- Safe to run in CI on untrusted model packages.
- Extensible via providers and emitters.

## Non-goals

- ORM object creation for Django/SQLAlchemy in v1.
- Networked data generation.
- Mutation testing or fuzzing beyond optional Hypothesis integration.

## Users and primary use cases

- Backend engineers: generate fixtures for unit and API tests.
- QA/contract testing: emit JSON examples to pin contracts and seed mock servers.
- Data eng/ML: create sample payloads for pipelines.
- OSS maintainers: publish example payloads in docs.

## Functional requirements

### Model discovery

- Inputs: module path (`pkg.models`), file path (`src/pkg/models.py`), or explicit `path.to:Model`.
- Enumerate subclasses of `pydantic.BaseModel` and `pydantic.RootModel`.
- Two modes:

  1. **Import mode (default):** import in a constrained subprocess.
  2. **AST mode:** parse classes to list candidates without importing; later import by name only if selected.

- Exclude/Include patterns, glob, and `--public-only`.
- Forward refs and circular deps resolution.

### Generation core

- Build a `Strategy` for each field using type info and Pydantic metadata: `Annotated`, `Field(ge, le, gt, lt, min_length, max_length, pattern, min_items, max_items, unique_items)`, constrained types (`conint`, `constr`, `conlist`, `condecimal`, `EmailStr`, `IPvAnyAddress`, `PaymentCardNumber`, etc.).
- Handle `Union`, `Optional`, `Literal`, `Enum`, nested models, dataclasses.
- Defaults respected; allow `--ignore-defaults` to force fake values.
- `None` probability `p_none` per field (default 0.1) configurable globally and per field.
- Determinism: single seed drives `random`, Faker, NumPy (if present). Stable output for same inputs, seed, and tool version.
- Performance: streaming generation with chunked writes; worker pool for JSON sample emission.

### Type→provider mapping (core set)

- `str`: Faker text truncated to `max_length`; regex via optional `rstr` extra.
- `int`/`float`: bounded by constraints; `Decimal` quantized to `decimal_places` with `max_digits`.
- `bool`: random bool.
- `datetime`/`date`/`time`: bounded windows; timezone-aware using `zoneinfo`.
- `UUID`: uuid4; `AnyUrl`, `HttpUrl`, `EmailStr`, `IPvAny*`, `PaymentCardNumber`, `Color` via Faker providers.
- `list/tuple/set`: size in `[min_items,max_items]`, uniqueness enforced when requested.
- `dict`: keys from provider; values from mapped strategy.
- `SecretStr/Bytes`: Faker password or bytes.
- Fallback: raise with actionable hint unless `--allow-fallback` uses placeholder.

### Overrides and policies

- Per-model and per-field overrides in config and CLI: fixed value, custom provider, range tweaks.
- Union selection policy: `first|random|weighted` with weights.
- Enum/Literal policy: `first|random`.
- Referential density: limit recursion depth and total graph size.

### Emitters

- **pytest fixtures (codegen):**

  - Output to `tests/conftest.py` or module file.
  - Styles: function fixtures, factory functions, or class-based factory.
  - Scopes: `function|module|session`.
  - Return type: `Model` or `dict` via `.model_dump()`.
  - Parametrized fixtures `--cases N`.
  - Imports deduped; formatted with Black (via Ruff) on emit; type hints for MyPy/Pyright.
  - Header comment with seed, tool version, model digest.

- **JSON/JSONL samples:**

  - `--n`, `--jsonl`, `--indent 0|2`, `--orjson`.
  - Partitioned output `--shard-size`.
  - Schema export using Pydantic `model_json_schema()`.

- **Hypothesis (optional):**

  - Emit strategies for models (`st.builds(Model, ...)`) behind `[hypothesis]` extra.

### CLI

```
pfg list <module-or-file> [--ast] [--include ...] [--exclude ...]
pfg gen fixtures <module-or-model> --out tests/conftest.py --style functions --scope function --seed 42 --p-none 0.1
pfg gen json <module-or-model> --n 1000 --out samples/Model.jsonl --jsonl --seed 42 --indent 0
pfg gen schema <module-or-model> --out schema/Model.json
pfg doctor <module-or-file>  # report unmapped fields, cycles, risky imports
```

- Global flags: `--safe-import`, `--workers`, `--locale`, `--verbose`, `--dry-run`, `--fail-on-warn`.

### Configuration

- `pyproject.toml` section `[tool.pydantic_fixturegen]`.
- Keys: `seed`, `locale`, `include`, `exclude`, `p_none`, `union_policy`, `enum_policy`, `overrides.{Model}.{field}`, `emitters.pytest.style`, `emitters.pytest.scope`, `json.indent`, `json.orjson`.
- YAML config supported as alternative.
- Env var prefix `PFG_` mirrors keys.

### Plugins and extensibility

- Pluggy hook specs:

  - `pfg_register_providers(registry)`
  - `pfg_modify_strategy(model, field, strategy)`
  - `pfg_emit_artifact(kind, ctx)`

- Entry points:

  - `pydantic_fixturegen.providers`
  - `pydantic_fixturegen.emitters`

- Extras: `[django]`, `[sqlalchemy]`, `[hypothesis]`, `[regex]`, `[orjson]`.

### Safety

- **Safe import mode** (default true in CI): forked subprocess with:

  - `PYTHONSAFEPATH`, empty `PYTHONPATH` except project, cwd jail, `NO_PROXY=*`, network blocked via env and monkeypatch option.
  - Time limit and memory cap.

- AST listing avoids executing module code during discovery.
- No telemetry. No network.

### Logging and DX

- Rich console with levels.
- `pfg doctor` prints coverage table per type and flags unmapped constraints.
- `--explain` dumps chosen strategy per field.

### Errors

- Clear error codes:

  - `10` discovery error, `20` mapping error, `30` emit error, `40` unsafe import violation.

- Machine-readable `--json-errors` mode.

## Non-functional requirements

- Python 3.10–3.13. Linux, macOS, Windows.
- Generate 10k JSON objects of a medium model (20 fields, 3 nested) in ≤5 s on a laptop CPU; peak RSS ≤300 MB.
- Determinism test: identical outputs across two runs on same platform and version.
- Test coverage ≥90% lines. Type-check clean under MyPy strict.
- CLI startup time ≤200 ms warm.

## Architecture

### Modules

```
pydantic_fixturegen/
  cli/                 # Typer commands
  core/
    introspect.py      # discovery (import + AST)
    schema.py          # Pydantic helpers and constraints extraction
    strategies.py      # type→provider mapping
    generate.py        # recursive instance builder
    seed.py            # deterministic seed plumbing
  emitters/
    pytest_codegen.py
    json_out.py
    schema_out.py
  plugins/
  templates/
    fixtures.j2
    factory_module.j2
```

### Data flow

1. Discover models → 2) Build field strategies → 3) Generate instances stream → 4) Emit artifacts → 5) Format and write.

### Key algorithms

- Constraint synthesis: choose closed intervals for numeric types; enforce `exclusive` bounds by shifting by epsilon or integer step.
- Regex generation: if `pattern` present and `[regex]` extra installed, use generator; else warn or fallback.
- Cycle guard: maintain per-path depth and object budget; fall back to `None` or shallow reference when exceeded.
- Union choice: deterministic hash(model_path, field, seed, index) mod options when `random`.

## Deployment

### Packaging and release

- Build with Hatch. Wheels: universal pure-python.
- Publish to PyPI with GitHub Actions matrix (3.10–3.13; ubuntu/mac/win).
- Signed tags, Trusted Publishing.
- Extras: `[all]` aggregates common extras.
- Optional: Homebrew formula and winget manifest.
- Prebuilt GitHub Action `action.yml`:

  - `uses: org/pydantic-fixturegen-action@v1`
  - Inputs: `module`, `out`, `seed`, `n`.

### Installation

```
pip install pydantic-fixturegen[orjson]
# or with extras
pip install "pydantic-fixturegen[all]"
```

### CI usage

- Step to fail PRs if fixture drift detected:

```
pfg gen fixtures src/pkg/models --out tests/conftest.py
git diff --exit-code tests/conftest.py
```

- Step to refresh JSON samples and upload as artifacts.

## API surface (Python)

```python
from pydantic_fixturegen import generate_instances, emit_pytest_fixtures

list(generate_instances(Model, n=100, seed=42))  # yields Model
emit_pytest_fixtures([ModelA, ModelB], path="tests/conftest.py", style="functions")
```

## Configuration example (`pyproject.toml`)

```toml
[tool.pydantic_fixturegen]
seed = 1337
locale = "sv_SE"
include = ["app.models.*"]
exclude = ["app.models.internal.*"]
p_none = 0.05
union_policy = "weighted"
enum_policy = "first"

[tool.pydantic_fixturegen.overrides."app.models.User".email]
provider = "email"

[tool.pydantic_fixturegen.emitters.pytest]
style = "functions"
scope = "function"
return_type = "model"  # or "dict"
```

## Example outputs

### Generated fixture (functions style)

```python
# Generated by pydantic-fixturegen v0.1.0; seed=42; model=app.models.User
import pytest
from app.models import User
from datetime import datetime

@pytest.fixture(scope="function")
def user() -> User:
    return User(
        id="a3c2b3a4-7e12-4e0d-9d2c-6b2a1b9dcb1a",
        email="maria.larsson@example.com",
        created_at=datetime(2024, 5, 17, 9, 14, 3, tzinfo=timezone.utc),
        # ...
    )
```

### JSONL sample

```
{"id":"...","email":"...","created_at":"2024-05-17T09:14:03Z",...}
```

## Testing plan

- Unit tests per mapper and constraint.
- Golden tests for codegen with snapshot tooling.
- Determinism tests across two runs.
- Fuzz with Hypothesis for mapper invariants.
- E2E: run CLI against a sample project matrix.
- Security test: ensure no network calls during import; timeouts enforced.

## Metrics of success

- Time to first fixture ≤2 min for new project.
- Replace ≥80% of hand-written factories in target repo.
- CI time reduction on data generation tasks.
- Adoption: stars, PyPI downloads, issues from external users.

## Risks and mitigations

- Pydantic changes: pin tested versions and maintain adapters.
- Regex generation complexity: keep optional extra and clear fallbacks.
- Import side effects: default safe mode + AST discovery.
- Determinism across platforms: document OS and Python minor version caveats; embed metadata in artifacts.

## Definition of done

- CLI implements `list`, `gen fixtures`, `gen json`, `gen schema`, `doctor`.
- pyproject config schema validated.
- ≥90% coverage, strict types.
- Determinism proven, performance target met.
- Docs with quick start, cookbook, CI examples.
- Signed v0.1.0 on PyPI and tagged.
