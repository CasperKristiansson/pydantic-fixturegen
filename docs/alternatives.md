# Alternatives & migration guides

Compare popular fixture generators side-by-side, understand where pydantic-fixturegen shines, and borrow migration recipes when you are ready to switch.

## Detailed comparison

| Capability             | **pydantic-fixturegen**                                                                                                             | **Polyfactory**                                                          | **Pydantic-Factories**           | **factory_boy**                       |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------- | ------------------------------------- |
| Deterministic seeds    | Cascaded seeds across `random`, Faker, NumPy, PyArrow, SplitMix64 portable RNG, optional freeze files                               | Faker-only seeds; Python RNG drift between interpreters                  | Faker-only seeds; no freeze file | Manual or per-factory seeding         |
| Outputs                | JSON/JSONL, tabular datasets (CSV/Parquet/Arrow), pytest fixtures, schema emitters, Hypothesis strategies, anonymized payloads      | Python objects or dicts; JSON via `.dict()`                              | Python objects/dicts             | ORM models/objects                    |
| CLI & automation       | Full CLI suite (`list`, `gen`, `diff`, `check`, `doctor`, `explain`, `snapshot`, `lock`, `verify`) plus watch mode and JSON logging | Python API only                                                          | Python API only                  | Python API only                       |
| Sandboxing & CI        | Safe-import jail w/ timeout + memory caps, network/file system guards, `pfg snapshot verify` for CI                                 | No sandbox; factories run in-process                                     | No sandbox                       | No sandbox                            |
| Plugin/extension story | Pluggy hooks (`pfg_register_providers`, `pfg_modify_strategy`, `pfg_emit_artifact`), custom heuristics/providers, CLI extras        | Sub-class factories; limited extension beyond overriding Faker providers | Sub-class factories              | Sub-class factories + Faker overrides |
| Schema/OpenAPI         | Ingest JSON Schema/OpenAPI (via datamodel-code-generator), explain gaps, inject generated examples                                  | N/A                                                                      | N/A                              | N/A                                   |
| FastAPI/seeders        | Mock server, smoke tests, dataset emitters, SQLModel/Beanie seeders, Polyfactory delegation                                         | Core factories only (excellent delegation target)                        | Core factories only              | ORM factories only                    |

**TL;DR:** use Polyfactory or Pydantic-Factories when you want hand-authored class-based factories, and fixturegen when you need deterministic project-wide artefacts, CLIs, or schema integrations.

## Migration guides

### Polyfactory → pydantic-fixturegen

Goal: keep the existing factory surface but move the heavy lifting to fixturegen.

1. Enable factory delegation in configuration:

```toml
[tool.pydantic_fixturegen.polyfactory]
enabled = true
modules = ["app.factories"]  # where your ModelFactory subclasses live
prefer_delegation = true     # let fixturegen call into them when matching models
```

2. Run `pfg gen json ./models.py --out snapshots/users.json --include app.models.User --seed 42`. fixturegen will detect `UserFactory` and reuse its `.build()` logic while keeping deterministic seeds, relation links, and CLI ergonomics.
3. To migrate away from factories entirely, export equivalents once and remove the Polyfactory dependency:

```bash
pfg gen polyfactory ./models.py --out factories_pfg.py --seed 7 --prefer-fixturegen
```

`factories_pfg.py` exposes the same `ModelFactory` API but proxies through fixturegen’s `GenerationConfig`. Delete the custom Polyfactory factories in stages while reusing freeze files for CI.

### Pydantic-Factories / Faker scripts → preset-based generation

1. Translate “faker-heavy” defaults into presets:

```toml
[tool.pydantic_fixturegen.presets."marketing-demo"]
seed = 123
profile = "pii-safe"
include = ["marketing.*"]
# override specific providers
[[tool.pydantic_fixturegen.presets."marketing-demo".field_policies]]
target = "marketing.models.Campaign.slug"
provider = "string.slug"
```

2. Replace script invocations with CLI runs:

```bash
pfg gen fixtures marketing/models.py --preset marketing-demo --out tests/fixtures/test_marketing.py
pfg gen dataset marketing/models.py --preset marketing-demo --format parquet --count 500
```

3. If you need to keep Hypothesis strategies, swap direct `pydantic_factories.ModelFactory.build()` calls for `pydantic_fixturegen.hypothesis.strategy_for(Model)` or the CLI exporter `pfg gen strategies`.

### Faker-only factories → providers & heuristics

| Old approach                        | Fixturegen equivalent                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| Faker seeding via `Faker.seed(123)` | `pfg gen ... --seed 123 --rng-mode portable`                                 |
| Hard-coded email domains            | Configure `[identifiers].email_domain = "example.org"` or add a field policy |
| Custom relationship wiring          | Declare `--link models.Order.user_id=models.User.id` or set `[relations]`    |

Once the deterministic config exists, you can reuse it everywhere: CLI, FastAPI mock server, anonymizer, or pytest plugin.

## Case studies & CI stories

### API teams shipping schema contracts

- **Problem:** Backends expose 60+ Pydantic models via OpenAPI. Frontend and QA teams needed nightly snapshots with concrete payloads and diff protection.
- **Solution:** `pfg gen json --schema openapi.yaml --out snapshots/{model}.json --freeze-seeds`. CI runs `pfg snapshot verify --json-out snapshots/{model}.json` and fails when contracts drift. Deterministic seeds let QA diff failing fields quickly.
- **Outcome:** Two hours less manual review per release, reproducible diffs in PRs.

### Data-science org migrating from Polyfactory

- **Problem:** Polyfactory factories produced great objects but lacked CLI surface and schema coverage. Engineers duplicated logic in scripts.
- **Solution:** Enabled Polyfactory delegation + freeze files to keep existing factories, then shortened them by delegating to fixturegen’s heuristics. Added `pfg gen dataset` to stream Parquet test data and `pfg lock` to guard provider coverage.
- **Outcome:** Same factories work, but teams now regenerate deterministic datasets and fixtures via CI without bespoke scripts.

### Privacy-heavy consumer app

- **Problem:** Needed anonymized JSON derived from production data plus deterministic regression tests.
- **Solution:** `pfg anonymize` rewrites raw payloads, `pfg snapshot verify` enforces drift budgets, and the anonymized outputs feed `pfg doctor` for coverage. Sandbox prevented production credentials from leaking during test discovery.

## Surface the comparison in docs

- Quick tour? Start with [features](features.md) or the [quickstart](quickstart.md).
- Evaluating alternatives? Bookmark this page and link it in design docs or RFCs.
- Ready to adopt? Follow the migration recipes above, run `pfg snapshot write` once, and wire the snapshots into CI.

When you need deterministic JSON/JSONL, pytest fixtures, schema artefacts, and CLI guardrails, fixturegen keeps everything in one toolchain. Use Polyfactory/Pydantic-Factories when you want hand-authored factory classes or interactive prototyping, and reach for fixturegen when those factories need to power reproducible pipelines.
