# pydantic-fixturegen: deterministic fixtures for Pydantic, dataclasses, TypedDicts

> Deterministic fixtures, pytest modules, datasets, and JSON from Pydantic v2 models **and** stdlib dataclasses/TypedDicts, all inside a sandboxed CLI with Pluggy providers.

[![PyPI version](https://img.shields.io/pypi/v/pydantic-fixturegen.svg "PyPI")](https://pypi.org/project/pydantic-fixturegen/)
[![Python versions](https://img.shields.io/pypi/pyversions/pydantic-fixturegen.svg "Python 3.10–3.14")](#support)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-blue)](#support)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg "MIT License")

Generate deterministic structured data, pytest fixtures, and JSON quickly with a safe, task-focused CLI built for modern testing workflows. Fixturegen still speaks Pydantic natively and now understands dataclasses and TypedDicts without extra adapters. Official support targets Python 3.10–3.14 and Pydantic v2.

📘 Read the full docs and examples at [pydantic-fixturegen.kitgrid.dev](https://pydantic-fixturegen.kitgrid.dev/).

## Install

```bash
pip install pydantic-fixturegen
# Extras: orjson, regex, hypothesis, watch
pip install 'pydantic-fixturegen[all]'
```

Other flows → [docs/install.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/install.md)

## ⚡️ 60-second quickstart

Copy/paste the snippet below into a shell. It drops a tiny `User` model into `models.py`, lists it, generates JSON samples, and writes pytest fixtures—all with deterministic seeds.

```bash
# 1) Create a minimal model file
cat > models.py <<'PY'
from pydantic import BaseModel, EmailStr


class User(BaseModel):
    id: int
    email: EmailStr
    tags: list[str]
PY

# 2) Discover models
pfg list models.py

# 3) Emit JSON samples (2 records) to ./out/User.json
pfg gen json models.py \
  --include models.User \
  --n 2 --indent 2 \
  --seed 7 --freeze-seeds \
  --out out/{model}.json

# 4) Emit pytest fixtures with 3 deterministic cases
pfg gen fixtures models.py \
  --include models.User \
  --cases 3 \
  --seed 7 --freeze-seeds \
  --out tests/fixtures/{model}_fixtures.py
```

Expected results:

- `pfg list` prints `models.User` so you know discovery works.
- `out/User.json` contains two pretty-printed user records seeded with `--seed 7`.
- `tests/fixtures/User_fixtures.py` exposes three pytest fixtures (`user_case_1`, etc.) you can import immediately.

Once those commands work, swap in your actual module path and tweak shared flags like `--include`, `--seed`, `--watch`, or `--cases` as needed.

## Why

<a id="why"></a>
<a id="features"></a>

- You keep tests reproducible with cascaded seeds across `random`, Faker, and optional NumPy.
- You run untrusted models inside a safe-import sandbox with network, filesystem, and memory guards.
- You drive JSON, pytest fixtures, schemas, and explanations from the CLI or Python helpers.
- You dial collection sizes up or down (globally or per field) with deterministic min/max/distribution knobs when you need denser samples.
- You extend generation with Pluggy providers and preset bundles without forking core code.

You also stay observant while you work: every command can emit structured logs, diff artifacts against disk, and surface sandbox warnings so you catch regressions before they land.

## Quick start

<a id="quickstart"></a>

1. Create a small model file (Pydantic v2, `@dataclass`, or `TypedDict`).
2. List models: `pfg list ./models.py`
3. Generate JSON: `pfg gen json ./models.py --include models.User --n 2 --indent 2 --out ./out/User`
4. Generate fixtures: `pfg gen fixtures ./models.py --out tests/fixtures/test_user.py --cases 3`
   Full steps → [docs/quickstart.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md)

JSON, fixtures, and schema commands all share flags like `--include`, `--exclude`, `--seed`, `--preset`, and `--watch`, so once you learn one flow you can handle the rest without re-reading the help pages.

### Example module + CLI tour

```python
# examples/models.py
from dataclasses import dataclass
from typing import TypedDict

from pydantic import BaseModel, EmailStr


class AuditTrail(TypedDict):
    actor: str
    event: str
    ip: str


@dataclass
class ShippingWindow:
    earliest: str
    latest: str


class Order(BaseModel):
    id: int
    email: EmailStr
    items: list[str]
    shipping: ShippingWindow
    audit: AuditTrail


class Address(BaseModel):
    street: str
    city: str
```

```bash
# JSON + datasets
pfg gen json examples/models.py --include examples.Order --n 5 --jsonl \
  --seed 11 --freeze-seeds \
  --out artifacts/{model}.jsonl
pfg gen dataset examples/models.py --include examples.Order --format parquet --n 10000 \
  --seed 11 --freeze-seeds \
  --out warehouse/{model}.parquet

# Pytest fixtures + persistence
pfg gen fixtures examples/models.py --include examples.Order --cases 3 \
  --seed 11 --freeze-seeds \
  --out tests/fixtures/{model}_fixtures.py
pfg persist examples/models.py --handler http-post --handler-config '{"url": "https://api.example.com/orders"}' \
  --include examples.Order --n 25 --seed 11 --freeze-seeds
```

Prefer Python APIs?

```python
from pathlib import Path
from pydantic_fixturegen.api import generate_json
from pydantic_fixturegen.core.path_template import OutputTemplate

result = generate_json(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("artifacts/{model}.json"),
    count=10,
    jsonl=True,
    include=["examples.Order"],
    field_hints="defaults",
    collection_min_items=1,
    collection_max_items=3,
)

for path in result.paths:
    print("wrote", path)
```

See [docs/examples.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/examples.md) for more end-to-end snippets that cover datasets, fixtures, persistence handlers, and Python helpers.

### Supported model families

- ✅ **Pydantic BaseModel / RootModel (v2)** — full support with validators, constraints, provider defaults, and Polyfactory delegation.
- ✅ **Stdlib `@dataclass`** — fixturegen inspects field metadata/annotations, respects defaults/examples, and serializes back to dataclass instances.
- ✅ **`typing.TypedDict` (total or partial)** — treated as schema-driven dicts, including nested dataclasses or other TypedDicts.
- 🚧 **attrs/msgspec** — not yet wired into the adapters; vote on [issue #53](https://github.com/CasperKristiansson/pydantic-fixturegen/issues/53) if you need them next.

The same include/exclude filters, overrides, presets, and field hints apply no matter which model family you point the CLI at.

## Basics

### Core usage (top 5)

<a id="cli"></a>

```bash
pfg list <path>
pfg gen json <target> [--n --jsonl --indent --out]
pfg gen fixtures <target> [--style --scope --cases --out]
pfg gen schema <target> --out <file>
pfg doctor <target>
```

- `pfg list` discovers models with AST or safe-import; add `--ast` when you must avoid imports.
- `pfg gen json` emits JSON or JSONL; scale with `--n`, `--jsonl`, `--shard-size`, and `--freeze-seeds`.
- `pfg gen fixtures` writes pytest modules; tune `--style`, `--scope`, `--cases`, and `--return-type`.
- `pfg gen schema` dumps JSON Schema atomically; point `--out` at a file or directory template.
- `pfg doctor` audits coverage and sandbox warnings; fail builds with `--fail-on-gaps`.

All commands → [docs/cli.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md)

### Basic configuration

<a id="configuration-precedence"></a>

| key                   | type             | default   | purpose       |
| --------------------- | ---------------- | --------- | ------------- |
| seed                  | int \ str \ null | null      | Global seed   |
| locale                | str              | en_US     | Faker locale  |
| union_policy          | enum             | first     | Union branch  |
| enum_policy           | enum             | first     | Enum choice   |
| json.indent           | int              | 2         | Pretty JSON   |
| json.orjson           | bool             | false     | Fast JSON     |
| emitters.pytest.style | enum             | functions | Fixture style |
| emitters.pytest.scope | enum             | function  | Fixture scope |

```toml
[tool.pydantic_fixturegen]
seed = 42
[tool.pydantic_fixturegen.json]
indent = 2
```

Need denser lists/sets? Add a `[tool.pydantic_fixturegen.collections]` block (or pass `--collection-*` flags) to clamp global min/max items and choose `uniform`, `min-heavy`, or `max-heavy` distributions before per-field constraints kick in.

Full matrix and precedence → [docs/configuration.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md)

### Common tasks

- Freeze seeds for CI determinism → [docs/seeds.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md)
- Use watch mode → [docs/quickstart.md#watch-mode](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md#watch-mode)
- Templated output paths → [docs/output-paths.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/output-paths.md)
- Provider customization → [docs/providers.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md)
- Capture explain trees or JSON diagnostics for review → [docs/explain.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/explain.md)

## Documentation

<a id="next-steps"></a>
<a id="architecture"></a>
<a id="comparison"></a>

[Index](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/index.md) · [Quickstart](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md) · [Examples](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/examples.md) · [Cookbook](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md) · [Configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md) · [CLI](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md) · [Concepts](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/concepts.md) · [Features](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/features.md) · [Security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md) · [Architecture](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/architecture.md) · [Troubleshooting](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/troubleshooting.md) · [Alternatives](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/alternatives.md)

## Community

<a id="community"></a>

Open issues for bugs or ideas, start Discussions for design questions, and follow the security policy when you disclose sandbox bypasses.

## License

<a id="license"></a>

MIT. See [`LICENSE`](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/LICENSE).
