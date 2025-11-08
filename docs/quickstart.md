# Quick start: Build deterministic Pydantic fixtures fast

> Follow one file from discovery to fixtures, learn config precedence, and watch artifacts regenerate on change.

## You need

- Python 3.10–3.14.
- `pip install pydantic-fixturegen` (add extras like `orjson`, `regex`, `hypothesis`, or `watch` as needed).
- A small Pydantic v2 model module.

## Step 1 — Create a model file

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

You can drop this file alongside your test suite or inside a sample project root.

## Step 2 — Discover models

```bash
pfg list ./models.py
```

You see fully-qualified names such as:

```text
models.User
models.Address
```

Use `--include`/`--exclude` to target specific classes, `--public-only` to respect `__all__`, or `--ast` when imports are unsafe.
Machine-readable errors are available with `--json-errors`; discovery failures surface error code `20`.

## Step 3 — Generate JSON artifacts

```bash
pfg gen json ./models.py --include models.User --n 2 --indent 2 --out ./out/User
```

- `--include` narrows generation when the module exposes many models.
- `--out` accepts template placeholders like `{model}`, `{case_index}`, and `{timestamp}`.
- `--indent` adds a metadata banner containing `seed`, `version`, and `digest`.
- Add `--jsonl` and `--shard-size` when you stream large datasets.

The command writes `out/User.json` with deterministic content:

```json
/* seed=42 version=1.0.0 digest=<sha256> */
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

## Step 4 — Emit pytest fixtures

```bash
pfg gen fixtures ./models.py \
  --out tests/fixtures/test_user_fixtures.py \
  --style functions --scope module --cases 3 --return-type model
```

You receive a formatted module with deduplicated imports and a banner:

```python
# pydantic-fixturegen v1.0.0  seed=42  digest=<sha256>
import pytest
from models import User, Address

@pytest.fixture(scope="module", params=[0, 1, 2], ids=lambda i: f"user_case_{i}")
def user(request) -> User:
    ...
```

Tune `--style` (`functions`, `factory`, `class`), `--scope` (`function`, `module`, `session`), and `--return-type` (`model`, `dict`) to match your test style.
Add `--p-none` to bias optional fields.

## Step 5 — Export JSON Schema

```bash
pfg gen schema ./models.py --out ./schema
```

Schema files write atomically to avoid partial artifacts.
Combine with `--watch` to rebuild on file changes.

## Step 6 — Explain generation strategies

```bash
pfg gen explain ./models.py --tree
```

You see an ASCII tree per field. Switch to machine-readable output with `--json`, cap recursion with `--max-depth`, and limit models with `--include` or `--exclude`.

```text
User
 ├─ id: int ← number_provider(int)
 ├─ name: str ← string_provider
 ├─ nickname: Optional[str] ← union(p_none=0.25)
 └─ address: Address ← nested model
```

Use this view to confirm plugin overrides or preset tweaks.

## Watch mode

<a id="watch-mode"></a>

Install the `watch` extra, then run:

```bash
pip install 'pydantic-fixturegen[watch]'
pfg gen json ./models.py --out ./out/User.json --watch
```

- The CLI monitors Python and configuration files beneath the working directory.
- `--watch-debounce <seconds>` controls the filesystem event throttle (default `0.5`).
- Combine with `--freeze-seeds` to keep deterministic outputs even as models change.

Watch mode is available on `gen json`, `gen fixtures`, and `gen schema`.

## Configuration checkpoints

- Run `pfg init` to scaffold `[tool.pydantic_fixturegen]` with sensible defaults (seed `42`, union policy `weighted`, enum policy `random`, pytest scope `module`).
- The precedence order is `CLI > environment (PFG_*) > pyproject.toml/YAML > defaults`.
- Reference the schema directly with `pfg schema config --out schema/config.schema.json`.
- Use `.pfg-seeds.json` with `--freeze-seeds` for reproducible CI runs; see [docs/seeds.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md).

## Quick command reference

```bash
# Scaffold configuration files
pfg init --yaml

# Diff regenerated artifacts against stored outputs
pfg diff models.py --json-out out/current.json --show-diff

# Validate configuration without generating artifacts
pfg check models.py --json-errors

# Regenerate JSON automatically (requires [watch] extra)
pfg gen json models.py --out out/models.json --watch

# Export configuration schema
pfg schema config --out schema/config.schema.json
```

## Troubleshooting tips

- Discovery import errors? Switch to `--ast` or fix `PYTHONPATH`. Capture machine-readable details with `--json-errors`.
- Non-deterministic outputs? Pin `--seed` or `PFG_SEED` and inspect banner metadata.
- Large files choking CI? Use `--jsonl` and `--shard-size`, or enable `--orjson` via the `orjson` extra.
- Optional fields feel off? Adjust `--p-none` or configure `field_policies` in `pyproject.toml`.
- Sandbox blocked a write or socket? Move output beneath the working directory; network calls are intentionally disabled.

Next: explore deeper recipes in the [Cookbook](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md) or tighten config options in the [Configuration guide](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md).
