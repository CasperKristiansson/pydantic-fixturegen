# pydantic-fixturegen: deterministic Pydantic fixtures, JSON generator, secure sandbox

> Pydantic v2 deterministic fixtures, pytest fixtures, JSON generator, secure sandboxed CLI with Pluggy providers.

[![PyPI version](https://img.shields.io/pypi/v/pydantic-fixturegen.svg "PyPI")](https://pypi.org/project/pydantic-fixturegen/)
![Python versions](https://img.shields.io/pypi/pyversions/pydantic-fixturegen.svg "Python 3.10–3.14")
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg "MIT License")

Generate deterministic Pydantic v2 data, pytest fixtures, and JSON quickly with a safe, task-focused CLI built for modern testing workflows.

📘 Read the full docs and examples at [pydantic-fixturegen.kitgrid.dev](https://pydantic-fixturegen.kitgrid.dev/).

## Why

<a id="why"></a>
<a id="features"></a>

- You keep tests reproducible with cascaded seeds across `random`, Faker, and optional NumPy.
- You run untrusted models inside a safe-import sandbox with network, filesystem, and memory guards.
- You drive JSON, pytest fixtures, schemas, and explanations from the CLI or Python helpers.
- You extend generation with Pluggy providers and preset bundles without forking core code.

You also stay observant while you work: every command can emit structured logs, diff artifacts against disk, and surface sandbox warnings so you catch regressions before they land.

## Install

```bash
pip install pydantic-fixturegen
# Extras: orjson, regex, hypothesis, watch
pip install 'pydantic-fixturegen[all]'
```

Other flows → [docs/install.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/install.md)

## Quick start

<a id="quickstart"></a>

1. Create a small Pydantic v2 model file.
2. List models: `pfg list ./models.py`
3. Generate JSON: `pfg gen json ./models.py --include models.User --n 2 --indent 2 --out ./out/User`
4. Generate fixtures: `pfg gen fixtures ./models.py --out tests/fixtures/test_user.py --cases 3`
   Full steps → [docs/quickstart.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md)

JSON, fixtures, and schema commands all share flags like `--include`, `--exclude`, `--seed`, `--preset`, and `--watch`, so once you learn one flow you can handle the rest without re-reading the help pages.

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

[Index](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/index.md) · [Quickstart](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md) · [Cookbook](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md) · [Configuration](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md) · [CLI](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md) · [Concepts](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/concepts.md) · [Features](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/features.md) · [Security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md) · [Architecture](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/architecture.md) · [Troubleshooting](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/troubleshooting.md) · [Alternatives](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/alternatives.md)

## Community

<a id="community"></a>

Open issues for bugs or ideas, start Discussions for design questions, and follow the security policy when you disclose sandbox bypasses.

## License

<a id="license"></a>

MIT. See [`LICENSE`](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/LICENSE).
