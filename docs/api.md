# Python API: call generators from code

> Use the same engine as the CLI while staying inside Python workflows.

Import helpers directly:

```python
from pydantic_fixturegen.api import (
    generate_json,
    generate_fixtures,
    generate_schema,
    JsonGenerationResult,
    FixturesGenerationResult,
    SchemaGenerationResult,
)
```

## `generate_json`

```python
result: JsonGenerationResult = generate_json(
    "./models.py",
    out="artifacts/{model}/sample-{case_index}.json",
    count=3,
    jsonl=True,
    indent=0,
    use_orjson=True,
    shard_size=1000,
    include=["app.models.User"],
    seed=42,
    preset="boundary",
    freeze_seeds=True,
    freeze_seeds_file=".pfg-seeds.json",
)
```

- Parameters mirror `pfg gen json`.
- `out` accepts the same templated placeholders as the CLI.
- `freeze_seeds` and `freeze_seeds_file` manage deterministic per-model seeds.
- Supply `type_annotation=list[EmailStr]` (and optionally `type_label`) when you want to generate raw TypeAdapter outputs without pointing at a module. This mode mirrors the CLI `--type` option and cannot be mixed with relation helpers or seed freezing.
- The result exposes `paths`, `base_output`, the selected `model`, a `ConfigSnapshot`, and any warnings.

## `generate_fixtures`

```python
fixtures: FixturesGenerationResult = generate_fixtures(
    "./models.py",
    out="tests/fixtures/{model}_fixtures.py",
    style="factory",
    scope="session",
    cases=5,
    return_type="dict",
    seed=42,
    p_none=0.2,
    include=["app.models.User"],
    preset="boundary-max",
)
```

- Mirrors `pfg gen fixtures` options.
- Returns the path that was written (or `None` when skipped), resolved `style`, `scope`, `return_type`, and `cases`.
- Inspect `fixtures.metadata` for banner details such as digest and version.

## `generate_schema`

```python
schema: SchemaGenerationResult = generate_schema(
    "./models.py",
    out="schema/{model}.json",
    indent=2,
    include=["app.models.User", "app.models.Address"],
)
```

- Writes JSON Schema files atomically.
- The result lists discovered `models`, shared config, and warnings.

## Using the results

Each result dataclass includes:

- `paths` or `path` — filesystem locations written to disk.
- `base_output` — the original template base path for reference.
- `config` — `ConfigSnapshot` capturing seed, include/exclude patterns, and time anchor.
- `warnings` — tuple of warning identifiers surfaced during generation.
- `constraint_summary` (where applicable) — per-field constraint reports when constraints fail.
- `delegated` — indicates whether generation was handled by a plugin.

Because results are dataclasses, you can serialize them to JSON easily:

```python
from dataclasses import asdict

summary = asdict(fixtures)
```

Use these helpers inside build steps, pre-commit hooks, or custom orchestration without shelling out to the CLI. Pair them with [logging](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/logging.md) if you need structured telemetry from embedded runs.
