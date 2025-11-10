# Python API reference

> Use the same deterministic engine as the CLI without shelling out.

```python
from pathlib import Path
from pydantic_fixturegen.api import (
    generate_json,
    generate_dataset,
    generate_fixtures,
    generate_schema,
    DatasetGenerationResult,
    JsonGenerationResult,
    FixturesGenerationResult,
    SchemaGenerationResult,
    anonymize_payloads,
    anonymize_from_rules,
)
```

All helpers return dataclasses defined in `pydantic_fixturegen.api.models`. Every result exposes:

- `paths` / `path` — filesystem locations written atomically.
- `base_output` — the resolved template root (`OutputTemplateContext`).
- `config` — `ConfigSnapshot` capturing seed, include/exclude, RNG mode, time anchor, etc.
- `warnings` — tuple of warning strings (`("provider_missing", "relation_warning", ...)`).
- `constraint_summary` — field-level reports (when applicable).
- `delegated` — `True` when a plugin handled generation (e.g., Polyfactory delegate).

Because these are dataclasses you can `dataclasses.asdict(result)` for logging or JSON serialization.

## Generation helpers

### `generate_json`

```python
result: JsonGenerationResult = generate_json(
    "./models.py",
    out="artifacts/{model}/sample-{case_index}.json",
    count=5,
    jsonl=True,
    indent=0,
    use_orjson=True,
    shard_size=1000,
    include=["app.models.User"],
    exclude=["app.models.Legacy*"],
    seed=42,
    preset="boundary",
    profile="pii-safe",
    freeze_seeds=True,
    freeze_seeds_file=".pfg-seeds.json",
    now="2025-11-08T12:00:00Z",
    type_annotation=None,
)
```

| Parameter                                              | Type                | Notes                                                                                                                                   |
| ------------------------------------------------------ | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `target`                                               | `str`/`Path`/`None` | Module file that exports Pydantic models. Set to `None` when using `type_annotation`.                                                   |
| `out`                                                  | `str`/`Path`        | Templated `OutputTemplate` path (`{model}`, `{case_index}`, `{timestamp}` etc.).                                                        |
| `count`, `jsonl`, `indent`, `use_orjson`, `shard_size` | Scalars             | Match the CLI flags (`--n`, `--jsonl`, `--indent`, `--orjson`, `--shard-size`).                                                         |
| `include` / `exclude`                                  | sequence            | Fully-qualified model globs.                                                                                                            |
| `seed`, `preset`, `profile`                            | scalars             | Deterministic knobs identical to the CLI.                                                                                               |
| `freeze_seeds`, `freeze_seeds_file`                    | bool / path         | Manage per-model seeds via `.pfg-seeds.json`.                                                                                           |
| `now`                                                  | ISO timestamp       | Overrides the deterministic “current time” anchor.                                                                                      |
| `type_annotation`, `type_label`                        | any                 | Generate data for arbitrary type expressions (mirrors `pfg gen json --type`). Cannot be combined with relation helpers or freeze files. |

Return fields: `paths` (tuple of written files), `base_output`, `model` (when exactly one model was emitted), `config`, `warnings`.

### `generate_dataset`

```python
dataset: DatasetGenerationResult = generate_dataset(
    "./models.py",
    out="warehouse/{model}-{case_index}.parquet",
    count=250_000,
    format="parquet",
    shard_size=25_000,
    compression="zstd",
    include=["app.models.User"],
    seed=7,
    preset="boundary-max",
    freeze_seeds=True,
    preset="boundary-max",
    profile="realistic",
    respect_validators=True,
    validator_max_retries=3,
    relations={"app.models.Order.user_id": "app.models.User.id"},
    max_depth=4,
    cycle_policy="reuse",
    rng_mode="portable",
)
```

| Parameter                                     | Type                | Notes                                                                             |
| --------------------------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| `format`                                      | `str`               | `"csv"`, `"parquet"`, or `"arrow"`. Requires the `dataset` extra for PyArrow.     |
| `compression`                                 | `str`/`None`        | `"gzip"` for CSV, `"snappy"`, `"zstd"`, `"brotli"`, `"lz4"` for columnar formats. |
| `relations`                                   | `Mapping[str, str]` | Equivalent to CLI `--link`.                                                       |
| `respect_validators`, `validator_max_retries` | bool/int            | Enforce model validators with bounded retries.                                    |
| `max_depth`, `cycle_policy`, `rng_mode`       | scalars             | Mirror CLI recursion + RNG controls.                                              |

The result mirrors `JsonGenerationResult` but includes dataset-specific metadata about shard counts and `format`.

### `generate_fixtures`

```python
fixtures = generate_fixtures(
    "./models.py",
    out="tests/fixtures/{model}_fixtures.py",
    style="factory",
    scope="session",
    cases=4,
    return_type="dict",
    seed=99,
    p_none=0.35,
    include=["app.models.User"],
    preset="boundary",
    profile="pii-safe",
    freeze_seeds=True,
)
```

| Parameter     | Notes                                                            |
| ------------- | ---------------------------------------------------------------- |
| `style`       | `"functions"`, `"factory"`, or `"class"`. Mirrors CLI `--style`. |
| `scope`       | Pytest scope string (`"function"`, `"module"`, `"session"`).     |
| `cases`       | Number of parametrized cases per fixture.                        |
| `return_type` | `"model"` or `"dict"`.                                           |
| `p_none`      | Overrides optional field probability.                            |

Return values include `path` (written module), `metadata` (banner extras like digest, seed, style), and the resolved `style/scope/return_type/cases`.

### `generate_schema`

```python
schema = generate_schema(
    "./models.py",
    out="schema/{model}.json",
    indent=2,
    include=["app.models.User", "app.models.Address"],
    profile="pii-safe",
)
```

Writes JSON Schema files atomically. `include`, `exclude`, and `profile` behave like the CLI. Useful for embedding schema generation into build scripts or documentation tooling.

## Anonymizer helpers

### `anonymize_payloads`

```python
from pathlib import Path
from pydantic_fixturegen.api import anonymize_payloads

sanitized = anonymize_payloads(
    payloads=[{"email": "alice@example.com", "name": "Alice"}],
    rules_path=Path("anonymize.toml"),
    profile="pii-safe",
    salt="rotation-2025-11",
    entity_field="account.id",
    max_required_misses=0,
    max_rule_failures=0,
)
```

| Parameter                                  | Notes                                                                                                               |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `payloads`                                 | Iterable of dicts or JSON strings. Use `anonymize_from_rules` when you want the CLI-style file/directory behaviour. |
| `rules_path`                               | TOML/YAML/JSON rules file describing matchers + strategies.                                                         |
| `profile`                                  | Optional preset layering (e.g., `pii-safe`, `realistic`).                                                           |
| `salt`, `entity_field`                     | Control deterministic hashing / pseudonyms.                                                                         |
| `max_required_misses`, `max_rule_failures` | Override privacy budgets.                                                                                           |

Returns a generator of sanitized payloads (same shape as input). Combine with the CLI to reuse reporting/diffing features.

### `anonymize_from_rules`

```python
anonymize_from_rules(
    source=Path("data/raw"),
    destination=Path("data/sanitized"),
    rules_path=Path("anonymize.toml"),
    profile="pii-safe",
    report_path=Path("reports/anonymize.json"),
    doctor_target=Path("models.py"),
)
```

- Mirrors `pfg anonymize` behaviour: accepts files or directories, mirrors structure under `destination`, writes optional JSON reports, and can pipe sanitized output into `pfg doctor` automatically.
- Use when you want the CLI ergonomics but need to call from Python (e.g., inside a custom build step or notebook).

## Tips

- Every helper accepts the same deterministic knobs as the CLI. When you add a new config key (seed, preset, privacy profile), you only need to set it once in `pyproject.toml` or `pydantic-fixturegen.toml`.
- Results are dataclasses; call `asdict(result)` or `result.model_dump()` (via Pydantic) when you want to serialize metadata to JSON logs.
- Combine these helpers with the [`logging`](logging.md) reference to emit JSON logs from embedded runs, and with [`testing`](testing.md) when you want to drive pytest snapshots from code instead of shell scripts.
