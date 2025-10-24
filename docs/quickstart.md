---
title: "Quickstart — Deterministic Pydantic fixtures with a secure CLI"
description: "Evaluate pydantic-fixturegen in 5 minutes: install, generate deterministic JSON, emit pytest fixtures, and enable the safe-import sandbox."
keywords:
  - "pydantic fixtures"
  - "deterministic test data"
  - "pytest fixture generator"
  - "test data orchestration"
  - "generate deterministic JSON from Pydantic models"
  - "secure safe-import sandbox for Pydantic"
last_updated: "2025-01-01"
---

# Quickstart: Generate deterministic Pydantic fixtures in minutes (quickstart)

> Install, list models, generate deterministic JSON and pytest fixtures, and learn the sandbox and config precedence.

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
- Track progress in **[`docs/tasks.md`](./tasks.md)**.
