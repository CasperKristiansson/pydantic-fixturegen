## README.md

title: "pydantic-fixturegen — Deterministic Pydantic fixtures and CLI"
description: "Deterministic test data and pytest fixtures for Pydantic v2 with a secure safe-import sandbox and Pluggy-powered providers."
keywords: ["pydantic fixtures","deterministic test data","pytest fixture generator","pydantic automation tooling","test data orchestration","generate deterministic JSON from Pydantic models","secure safe-import sandbox for Pydantic","Pluggy-powered data providers"]
last_updated: 2025-01-01

---

# pydantic-fixturegen: Deterministic Pydantic fixtures for fast, safe tests (pydantic-fixturegen)

> Deterministic Pydantic fixtures and JSON generation via a secure sandboxed CLI and Pluggy plugins.

[![PyPI version](https://img.shields.io/pypi/v/pydantic-fixturegen.svg "PyPI")](https://pypi.org/project/pydantic-fixturegen/)
![Python versions](https://img.shields.io/pypi/pyversions/pydantic-fixturegen.svg "Python 3.10–3.13")
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg "MIT License")
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue "Continuous Integration")

`pydantic-fixturegen` is a **deterministic data generation toolkit for Pydantic v2 models**. It discovers models, builds generation strategies, creates instances, and **emits artifacts**—JSON, **pytest fixtures**, and JSON Schema—through a composable CLI and a **Pluggy** plugin layer.

- **Deterministic seeds** cascade per model/field across Python `random`, **Faker**, and optional **NumPy** RNGs.
- **Safe-import sandbox** executes untrusted model modules with **network lockdown**, **filesystem jail**, and **resource caps**.
- **Emitters** write JSON/JSONL, pytest fixture modules, and schema files with **atomic writes** and reproducibility metadata.
- **Config precedence**: **CLI args** → **`PFG_*` env vars** → **`[tool.pydantic_fixturegen]`** in `pyproject.toml` or YAML → defaults.

---

## Why pydantic-fixturegen (why)

- **Deterministic test data** for reproducible CI.
- **Secure safe-import sandbox** for third-party models.
- **Pluggy-powered data providers** for extension without forks.
- **CLI first**: `pfg list | gen json | gen fixtures | gen schema | gen explain | doctor`.

---

## Features at a glance (features)

| Area           | Highlights                                                                                                                                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Discovery**  | `pfg list` via AST or sandboxed import; include/exclude patterns; public-only; machine-readable errors (`--json-errors`, code `20`).                                                                                      |
| **Generation** | Depth-first builder with recursion/instance budgets; per-field policies (enums/unions/`p_none`).                                                                                                                          |
| **Emitters**   | JSON/JSONL with optional **orjson**, sharding, metadata header when indenting; pytest fixtures with banner (seed/version/digest) and Ruff/Black formatting; JSON Schema via `model_json_schema()` with **atomic writes**. |
| **Providers**  | Built-in numbers, strings (regex via optional `rstr`), collections, temporal, identifiers. Extensible via `pfg_register_providers`.                                                                                       |
| **Strategies** | `core/strategies.py` merges schema, policies, and plugin adjustments (`pfg_modify_strategy`).                                                                                                                             |
| **Security**   | Sandbox blocks sockets, scrubs env (`NO_PROXY=*`, proxies cleared, `PYTHONSAFEPATH=1`), redirects HOME/tmp, jails filesystem writes, caps memory (`RLIMIT_AS`, `RLIMIT_DATA`), **timeout exit code 40**.                  |
| **Config**     | CLI > `PFG_*` env > `pyproject`/YAML > defaults. String booleans accepted (`true/false/1/0`).                                                                                                                             |
| **Quality**    | Mypy + Ruff; pytest across Linux/macOS/Windows, Python **3.10–3.13**; coverage ≥ **90%**.                                                                                                                                 |
| **Release**    | Hatch builds; GitHub Actions matrices; PyPI **Trusted Publishing** with signing + attestations.                                                                                                                           |

---

## Install (install)

### pip

```bash
pip install pydantic-fixturegen
# Extras
pip install 'pydantic-fixturegen[orjson]'
pip install 'pydantic-fixturegen[regex]'
pip install 'pydantic-fixturegen[hypothesis]'
pip install 'pydantic-fixturegen[all]'        # runtime extras bundle
pip install 'pydantic-fixturegen[all-dev]'    # dev tools + runtime extras
```

### Poetry

```bash
poetry add pydantic-fixturegen
poetry run pfg --help
```

### Hatch

```toml
# pyproject.toml
[project]
dependencies = ["pydantic-fixturegen"]
```

```bash
hatch run pfg --help
```

---

## 60-second quickstart (quickstart)

**1) Define models**

```python
# models.py
from pydantic import BaseModel

class Address(BaseModel):
    street: str

class User(BaseModel):
    id: int
    name: str
    nickname: str | None = None
    address: Address
```

**2) Discover models**

```bash
pfg list ./models.py
# outputs:
# models.User
# models.Address
```

**3) Generate JSON samples**

```bash
pfg gen json ./models.py --n 2 --indent 2 --out ./out
# writes out/user.json with a metadata header comment when indenting
```

Example file (excerpt):

```json
/* seed=42 version=0.0.1 digest=<sha256> */
[
  {
    "id": 1,
    "name": "Alice",
    "nickname": null,
    "address": { "street": "42 Main St" }
  },
  {
    "id": 2,
    "name": "Bob",
    "nickname": "b",
    "address": { "street": "1 Side Rd" }
  }
]
```

**4) Generate pytest fixtures**

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_user_fixtures.py \
  --style function --scope module --cases 3 --return-type model
# produces a module with a banner and deduped imports, formatted by Ruff/Black
```

Fixture excerpt:

```python
# pydantic-fixturegen v0.0.1  seed=42  digest=<sha256>
import pytest
from models import User, Address

@pytest.fixture(scope="module", params=[0,1,2], ids=lambda i: f"user_case_{i}")
def user(request) -> User:
    # deterministic across runs/machines
    ...
```

---

## Configuration precedence (configuration-precedence)

```toml
# pyproject.toml
[tool.pydantic_fixturegen]
seed = 42
locale = "en_US"
union_policy = "weighted"
enum_policy = "random"
emitters.json.indent = 2
emitters.json.orjson = false
fixtures.style = "function"
fixtures.scope = "module"
```

Environment variables mirror keys using `PFG_` (e.g., `PFG_SEED=99`). **CLI flags override everything**.

---

## CLI overview (cli)

- `pfg list <module_or_path>` — enumerate models (AST and/or sandboxed import).
- `pfg gen json <target>` — deterministic JSON/JSONL (`--n`, `--jsonl`, `--indent`, `--orjson/--no-orjson`, `--shard-size`, `--out`, `--seed`).
- `pfg gen schema <target>` — emit JSON Schema (`--out` required; atomic writes; `--json-errors`).
- `pfg gen fixtures <target>` — emit pytest fixtures (`--style {function,factory,class}`, `--scope {function,module,session}`, `--p-none`, `--cases`, `--return-type {model,dict}`).
- `pfg gen explain <target>` — print provider/strategy tree per field; optional `--json` if exposed.
- `pfg doctor <target>` — audit coverage, constraints, risky imports (`--fail-on-warn`, `--json-errors`).

---

## Architecture in one diagram (architecture)

```
Models → Discovery (AST ⟷ Safe-Import Sandbox) → Strategies (policies + hooks)
      → ProviderRegistry (built-ins + plugins) → Instance Builder
      → Emitters (JSON | Fixtures | Schema, atomic IO, worker pools)
      → Artifacts on disk (with seed/version/digest metadata)
```

**Sandbox guards**: sockets blocked; env scrubbed (`NO_PROXY=*`, proxies cleared, `PYTHONSAFEPATH=1`); HOME/tmp redirected; writes outside workdir denied; memory caps (`RLIMIT_AS`, `RLIMIT_DATA`); **timeout exit code 40**.

---

## Comparison: pydantic-fixturegen vs alternatives (comparison)

| Use Case                              | Learning Curve | Determinism                                        | Security Controls                       | Best Fit                                                             |
| ------------------------------------- | -------------- | -------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------- |
| **pydantic-fixturegen**               | Low            | Strong, cascaded seeds across `random`/Faker/NumPy | Sandbox, atomic IO, JSON error taxonomy | Teams needing **deterministic Pydantic fixtures** and CLI automation |
| Hand-written fixtures                 | Medium–High    | Depends on reviewer discipline                     | None by default                         | Small codebases with few models                                      |
| Factory libraries (e.g., factory_boy) | Medium         | Often stochastic unless manually seeded            | Varies, not sandboxed                   | App-level object factories where ORM integration is key              |
| `hypothesis.extra.pydantic`           | Medium–High    | Property-based, not fixed by default               | Not sandboxed                           | Generative testing exploring model spaces                            |

---

## Community & support (community)

- Issues and contributions are welcome. Open an issue for bugs or feature discussions, and submit PRs with tests and docs.
- Security posture includes a sandbox and atomic writes; please report any bypass findings responsibly.

---

## License (license)

MIT. See `LICENSE`.

---

## Next steps (next-steps)

- Start with the **[Quickstart](./docs/quickstart.md)**.
- Dive deeper with the **[Cookbook](./docs/cookbook.md)**.

---

## docs/quickstart.md

title: "Quickstart — Deterministic Pydantic fixtures with a secure CLI"
description: "Evaluate pydantic-fixturegen in 5 minutes: install, generate deterministic JSON, emit pytest fixtures, and enable the safe-import sandbox."
keywords: ["pydantic fixtures","deterministic test data","pytest fixture generator","test data orchestration","generate deterministic JSON from Pydantic models","secure safe-import sandbox for Pydantic"]
last_updated: 2025-01-01

---

# Quickstart: Generate deterministic Pydantic fixtures in minutes (quickstart)

> _Meta Description_: Install, list models, generate deterministic JSON and pytest fixtures, and learn the sandbox and config precedence.

---

## 1) Why this tool vs hand-written fixtures (value-proposition)

- **Deterministic test data**: a single seed cascades across `random`, Faker, and optional NumPy per model/field.
- **Secure**: safe-import sandbox blocks sockets, jails writes, and caps memory; timeouts exit with code **40**.
- **Automated**: CLI emits JSON/JSONL, pytest fixtures, and JSON Schema. Works in Linux/macOS/Windows, Python 3.10–3.13.
- **Extensible**: Pluggy hooks for providers, strategies, and emitters.

---

## 2) Installation matrix (install-the-cli)

| Tooling          | Command                                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **pip**          | `pip install pydantic-fixturegen`                                                                                                                                                     |
| **pip + extras** | `pip install 'pydantic-fixturegen[orjson]'` · `pip install 'pydantic-fixturegen[regex]'` · `pip install 'pydantic-fixturegen[hypothesis]'` · `pip install 'pydantic-fixturegen[all]'` |
| **Poetry**       | `poetry add pydantic-fixturegen` then `poetry run pfg --help`                                                                                                                         |
| **Hatch**        | Add `pydantic-fixturegen` to `project.dependencies`, then `hatch run pfg --help`                                                                                                      |

---

## 3) Five-minute guided tour (guided-tour)

### 3.1 Create a model (create-model)

```python
# models.py
from pydantic import BaseModel

class Address(BaseModel):
    street: str

class User(BaseModel):
    id: int
    name: str
    nickname: str | None = None
    address: Address
```

### 3.2 Discover models (discover)

```bash
pfg list ./models.py
```

**What it does**: Enumerates Pydantic v2 models via **AST** or **safe-import** (combined by default).
**Representative output**:

```
models.User
models.Address
```

### 3.3 Generate deterministic JSON (gen-json)

```bash
pfg gen json ./models.py --n 2 --indent 2 --out ./out
```

**What it does**: Builds two deterministic instances per model and writes pretty-printed JSON.
**Files written**:

- `out/User.json` with a **metadata header comment** containing `seed/version/digest` when `--indent` is used.

Example excerpt:

```json
/* seed=42 version=0.0.1 digest=<sha256> */
[
  {
    "id": 1,
    "name": "Alice",
    "nickname": null,
    "address": { "street": "42 Main St" }
  },
  {
    "id": 2,
    "name": "Bob",
    "nickname": "b",
    "address": { "street": "1 Side Rd" }
  }
]
```

### 3.4 Emit pytest fixtures (gen-fixtures)

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_user_fixtures.py \
  --style function --scope module --p-none 0.25 --cases 3 --return-type model
```

**What it does**: Outputs a fixture module with deduped imports and a banner holding `seed/version/digest`.
**Representative output snippet**:

```python
# pydantic-fixturegen v0.0.1  seed=42  digest=<sha256>
import pytest
from models import User, Address

@pytest.fixture(scope="module", params=[0,1,2])
def user(request) -> User:
    ...
```

### 3.5 Generate JSON Schema (gen-schema)

```bash
pfg gen schema ./models.py --out ./schema
```

**What it does**: Calls `model_json_schema()` and writes files **atomically** to avoid partial artifacts.

### 3.6 Explain strategy decisions (gen-explain)

```bash
pfg gen explain ./models.py
```

**What it does**: Prints a **provider/strategy tree** per field with active policies and plugin overrides.
**Example (textual)**:

```
User
 ├─ id: int ← number_provider(int)
 ├─ name: str ← string_provider
 ├─ nickname: Optional[str] ← union(p_none=0.25)
 └─ address: Address ← nested model
```

---

## 4) Configuration overview and precedence (configuration)

Add to `pyproject.toml`:

```toml
[tool.pydantic_fixturegen]
seed = 42
locale = "en_US"
union_policy = "weighted"
enum_policy = "random"
emitters.json.indent = 2
emitters.json.orjson = false
fixtures.style = "function"
fixtures.scope = "module"
```

**Environment variables**: Mirror keys with `PFG_` prefix, e.g.:

```bash
export PFG_SEED=99
export PFG_EMITTERS__JSON__INDENT=0
```

**CLI flags** always win:

```bash
pfg gen json ./models.py --seed 777 --indent 0
```

**Precedence summary**:

| Priority | Source                                                       |
| -------- | ------------------------------------------------------------ |
| 1        | **CLI arguments**                                            |
| 2        | **Environment** `PFG_*`                                      |
| 3        | **`[tool.pydantic_fixturegen]`** in `pyproject.toml` or YAML |
| 4        | Defaults                                                     |

---

## 5) Security & sandbox guarantees (security)

- **Network lockdown**: all socket constructors/functions monkey-patched to raise `RuntimeError`.
- **Env scrub**: `NO_PROXY=*`, proxies cleared, `PYTHONSAFEPATH=1`; HOME/tmp redirected into sandbox.
- **Filesystem jail**: `open`, `io.open`, `os.open` deny writes **outside** the working directory.
- **Resource caps**: `resource.RLIMIT_AS` and `RLIMIT_DATA` enforced where available.
- **Timeouts**: exceeded time returns **exit code 40**.
- Use `pfg doctor` to surface **risky imports** and **coverage gaps**; `--fail-on-warn` makes it CI-blocking.

---

## 6) Troubleshooting checklist (troubleshooting)

- **Discovery import error?** Use `--ast` to skip runtime import or fix import path. For machine output use `--json-errors`.
- **Non-deterministic outputs?** Pin `seed` via CLI or env; verify with banner/header metadata.
- **Large JSON files?** Use `--jsonl` and `--shard-size`; consider `--indent 0` or enable `--orjson`.
- **Optional fields too sparse/dense?** Tune `--p-none` or set it in `pyproject.toml`.
- **Schema writes partial?** `pfg gen schema` uses atomic writes; ensure destination is writable.
- **Socket/FS denied?** That is sandboxed by design. Keep generation within the working directory.

---

## Quick Reference (quick-reference)

```bash
# List models
pfg list <module_or_path>

# Deterministic JSON / JSONL
pfg gen json <target> --n 100 --jsonl --indent 2 --orjson --shard-size 1000 --out ./out --seed 42

# JSON Schema
pfg gen schema <target> --out ./schema --json-errors

# Pytest fixtures
pfg gen fixtures <target> --out tests/fixtures/test_models.py \
  --style {function,factory,class} --scope {function,module,session} \
  --p-none 0.1 --cases 3 --return-type {model,dict} --seed 42

# Explain strategy tree
pfg gen explain <target>   # textual tree; --json if exposed

# Doctor audit
pfg doctor <target> --fail-on-warn --json-errors
```

---

## Comparison table (comparison)

| Tooling                     | Determinism Guarantees           | Plugin Model                                                                            | Sandboxing                         | CLI Coverage                        | Best For                                      |
| --------------------------- | -------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------- | ----------------------------------- | --------------------------------------------- |
| **pydantic-fixturegen**     | Strong, cascaded seeds           | **Pluggy** hooks (`pfg_register_providers`, `pfg_modify_strategy`, `pfg_emit_artifact`) | **Yes** (network + FS jail + caps) | **Broad** (list/gen/explain/doctor) | Deterministic Pydantic fixtures and artifacts |
| factory_boy                 | Manual seeding                   | Extensible classes                                                                      | No                                 | N/A                                 | App factories tied to ORM                     |
| `hypothesis.extra.pydantic` | Generative, not fixed by default | Strategy composition                                                                    | No                                 | N/A                                 | Property-based exploration                    |

---

## Next steps (next-steps)

- Continue to the **[Cookbook](./cookbook.md)** for advanced recipes.
- Wire into CI using **[CI examples](./ci_examples.md)**.

---

## docs/cookbook.md

title: "Cookbook — Advanced recipes for pydantic-fixturegen"
description: "Strategy tuning, emitter options, plugin hooks, sandbox practices, and performance tips for deterministic Pydantic fixtures."
keywords: ["pydantic fixtures","pytest fixture generator","deterministic test data","pydantic automation tooling","test data orchestration","secure safe-import sandbox for Pydantic"]
last_updated: 2025-01-01

---

# Cookbook: Recipes for power users and plugin authors (cookbook)

> _Meta Description_: Strategy tuning, plugin hooks, emitter tricks, sandbox hardening, and performance for large test suites.

---

## Strategy personalization (strategy-personalization)

### Context

Adjust how values are produced—especially **enums**, **unions**, and **optionals**—without losing determinism.

### Prerequisites

- Installed `pydantic-fixturegen`.
- Your Pydantic v2 models.

### Steps

1. **Set global policies** in `pyproject.toml`:

   ```toml
   [tool.pydantic_fixturegen]
   enum_policy = "random"
   union_policy = "weighted"
   ```

2. **Tune optionality** on the CLI when generating fixtures:

   ```bash
   pfg gen fixtures ./models.py --p-none 0.2 --out tests/fixtures/test_models.py
   ```

3. **Inspect the decisions**:

   ```bash
   pfg gen explain ./models.py
   ```

   Example output:

   ```
   User.nickname: Optional[str] ← union p_none=0.2
   ```

### Verification

- Re-run the same command with the same seed and confirm identical outputs across machines.

### Why it matters

Consistent policies make flaky tests unlikely and reduce hand-tuning in each fixture.

---

## Overriding or extending providers (custom-providers)

### Context

Add domain-specific generators by hooking into the **ProviderRegistry** via Pluggy.

### Prerequisites

- A Python package (installable) that defines Pluggy hooks.

### Steps

1. **Create a plugin module** exposing the hooks:

   ```python
   # my_pfg_plugin/providers.py
   from pydantic_fixturegen.plugins import hookspecs

   def pfg_register_providers(registry):
       # Example: register a custom provider for a specific constrained type
       # registry.register("my_type", MyProvider())
       ...

   def pfg_modify_strategy(model_name, field_name, strategy):
       # Adjust constraints, weights, or policies per field
       return strategy

   def pfg_emit_artifact(artifact_type, path, context):
       # Observe or augment emission events if needed
       return None
   ```

2. **Install your package** so its entry point can be discovered at runtime.
3. **Generate data** as usual; your providers and strategy mods are applied.

### Verification

- Run `pfg gen explain <target>` and confirm fields use your provider or show modified policies.

### Why it matters

Plugins localize domain logic without forking the tool or hand-writing fixtures.

---

## Advanced emitters (advanced-emitters)

### Context

Control size, performance, and style of artifacts.

### Prerequisites

- Model module and output directory.

### Recipes

**A) Shard large JSON outputs**

```bash
pfg gen json ./models.py --n 100000 --jsonl --shard-size 1000 --out ./out
# Newline-delimited JSON with shard files: User-00001.jsonl, User-00002.jsonl, ...
```

**B) Toggle orjson for throughput**

```bash
pfg gen json ./models.py --orjson --indent 0 --out ./out
```

**C) Choose fixture style/scope and return type**

```bash
pfg gen fixtures ./models.py --style factory --scope session --return-type dict \
  --out tests/fixtures/test_models.py
```

**D) Atomic schema emission**

```bash
pfg gen schema ./models.py --out ./schema
# Uses temp file + rename to avoid partial writes
```

### Verification

- Inspect first lines for **seed/version/digest** in JSON (when indenting) or fixture banner.

### Why it matters

Right-sizing artifacts keeps CI fast while preserving determinism.

---

## Security-focused recipes (security-recipes)

### Context

Run untrusted model modules safely and catch risky patterns.

### Prerequisites

- Untrusted or third-party model code in a separate directory.

### Steps

1. **Prefer AST mode** during discovery when runtime import is unnecessary:

   ```bash
   pfg list ./third_party_models.py --ast
   ```

2. **Use the sandbox** for imports during generation:

   ```bash
   pfg gen json ./third_party_models.py --n 10 --out ./out
   ```

3. **Run the doctor** before CI:

   ```bash
   pfg doctor ./third_party_models.py --fail-on-warn
   ```

### Guarantees

- **Network lockdown**: socket calls raise `RuntimeError`.
- **Filesystem jail**: writes outside the working directory are denied.
- **Resource caps**: `RLIMIT_AS` and `RLIMIT_DATA` limit memory.
- **Timeouts**: exit code **40** signals a timed-out sandbox.

### Why it matters

You can evaluate community models without risking exfiltration or unstable CI.

---

## Performance optimization (performance)

### Context

Scale to large datasets with predictable memory and CPU.

### Prerequisites

- Sufficient CPU cores; consider enabling `orjson`.

### Steps

1. **Use worker pools for JSON** (enabled by the JSON emitter):

   ```bash
   pfg gen json ./models.py --n 200000 --jsonl --shard-size 5000 --out ./out
   ```

2. **Reduce formatting overhead**:

   ```bash
   pfg gen json ./models.py --indent 0 --orjson --out ./out
   ```

3. **Budget memory** with sharding and JSONL; avoid loading everything into RAM.

### Verification

- Measure wall time and file sizes; outputs remain deterministic given the same seed.

### Why it matters

Parallel-safe emitters plus sharding yield throughput without compromising reproducibility.

---

## Mermaid: plugin workflow (plugin-workflow)

```mermaid
flowchart TD
  CLI["pfg CLI"] --> D[Discovery<br/>(AST + Safe-Import)]
  D --> S[Strategies<br/>(policies + constraints)]
  S --> R[ProviderRegistry<br/>(built-ins + plugins)]
  R --> G[Instance Builder]
  G --> E[Emitters<br/>(JSON | Fixtures | Schema)]
  E --> A[(Artifacts on disk)]

  subgraph Plugin Hooks
    H1["pfg_register_providers"]
    H2["pfg_modify_strategy"]
    H3["pfg_emit_artifact"]
  end

  H1 --> R
  H2 --> S
  H3 --> E
```

---

## Extras matrix (extras-matrix)

| Extra                       | Capabilities Unlocked                                               | Install Command                                 | Ideal Use Case                                      |
| --------------------------- | ------------------------------------------------------------------- | ----------------------------------------------- | --------------------------------------------------- |
| `regex` → `rstr`            | String generation from regex patterns                               | `pip install 'pydantic-fixturegen[regex]'`      | Models with regex-constrained fields                |
| `orjson` → `orjson`         | High-throughput JSON encoding                                       | `pip install 'pydantic-fixturegen[orjson]'`     | Large JSON/JSONL dumps in CI                        |
| `hypothesis` → `hypothesis` | Property-based testing extras                                       | `pip install 'pydantic-fixturegen[hypothesis]'` | Complement deterministic runs with generative tests |
| `all`                       | All runtime extras                                                  | `pip install 'pydantic-fixturegen[all]'`        | One-shot enablement                                 |
| `all-dev`                   | Runtime extras + dev tools (`mypy`, `ruff`, `pytest`, `pytest-cov`) | `pip install 'pydantic-fixturegen[all-dev]'`    | Local development and contributions                 |

---

## FAQ (faq)

<details>
<summary>How is determinism guaranteed across runs and machines?</summary>
Seeds cascade deterministically per model and field across Python <code>random</code>, Faker, and optional NumPy RNGs. Keep the seed fixed via CLI or <code>PFG_SEED</code>. Banners/headers record <em>seed/version/digest</em> for verification.
</details>

<details>
<summary>Which configuration value “wins” if I set it in multiple places?</summary>
Precedence is strict: CLI args → <code>PFG_*</code> environment → <code>[tool.pydantic_fixturegen]</code> in <code>pyproject.toml</code> or YAML → defaults. Booleans accept <code>true/false/1/0</code>.
</details>

<details>
<summary>Can I change how a specific field is generated without forking?</summary>
Yes. Implement <code>pfg_modify_strategy</code> in a plugin to adjust the field’s strategy or constraints. Verify with <code>pfg gen explain</code>.
</details>

<details>
<summary>Is it safe to run against untrusted model modules?</summary>
Yes. The safe-import sandbox blocks network, jails writes, scrubs env, and caps memory; timeouts exit with code 40. Combine with <code>pfg doctor</code> and, if discovery suffices, use <code>--ast</code>.
</details>

<details>
<summary>How do I avoid partial schema files if generation fails?</summary>
The schema emitter writes to a temp file and renames atomically. You either get the old file or the new one—never a partial.
</details>

<details>
<summary>What if I need machine-readable errors in CI?</summary>
Use <code>--json-errors</code> on supported commands. Discovery failures return a JSON payload with code <code>20</code>.
</details>

---

## Next steps (next-steps)

- Browse the **[Quickstart](./quickstart.md)** for the core flow.
- Wire into pipelines via **[CI examples](./ci_examples.md)**.
- Track work items in **[`docs/tasks.md`](./tasks.md)**.

---
