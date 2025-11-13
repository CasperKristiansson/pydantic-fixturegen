# Examples: CLI and Python API

This page collects end-to-end snippets you can copy straight into a shell, notebook, or CI pipeline. Every section reuses the same miniature domain so you can mix-and-match commands without rewriting the models.

## Shared model module

```python
# examples/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from pydantic import BaseModel, EmailStr, Field


class AuditTrail(TypedDict):
    actor: str
    ip: str
    event: str


@dataclass
class ShippingWindow:
    earliest: str
    latest: str


class Address(BaseModel):
    street: str
    city: str
    country: str = Field(default="SE", pattern=r"^[A-Z]{2}$")


class Order(BaseModel):
    id: int
    email: EmailStr
    items: list[str]
    shipping: ShippingWindow
    audit: AuditTrail
    notes: list[str] = Field(default_factory=list, examples=[["Leave at reception"]])
```

Save the snippet as `examples/models.py` (or copy it into your repo) and point each command at that file.

## CLI flows

### JSON generation (with sharding + collection controls)

```bash
pfg gen json examples/models.py \
  --include examples.Order \
  --out artifacts/{model}/sample-{case_index}.json \
  --n 5 \
  --jsonl \
  --collection-min-items 2 \
  --collection-max-items 4 \
  --collection-distribution max-heavy \
  --field-hints defaults-then-examples \
  --seed 2025 --freeze-seeds
```

- `--jsonl` streams newline-delimited payloads per shard.
- The collection flags keep `items` and `notes` dense so tests cover multi-element logic.
- Freeze files make follow-up runs deterministic even if models change order inside the module.

### Dataset export (Parquet + compression)

```bash
pfg gen dataset examples/models.py \
  --include examples.Order \
  --format parquet \
  --compression zstd \
  --n 25000 \
  --shard-size 5000 \
  --out warehouse/{model}/{timestamp}.parquet \
  --collection-min-items 1 \
  --collection-max-items 3
```

PyArrow (installed via `pip install "pydantic-fixturegen[dataset]"`) handles the sharded Parquet files. Each file contains a `__cycles__` column so downstream consumers can tell when cycle policies triggered.

### Pytest fixtures with related models

```bash
pfg gen fixtures examples/models.py \
  --include examples.Order \
  --out tests/fixtures/{model}_fixtures.py \
  --style factory \
  --scope session \
  --cases 4 \
  --collection-max-items 2 \
  --with-related examples.Address
```

Fixtures emit deterministic `Order` + `Address` bundles (one dictionary per case) while respecting the global collection policy.

### Persistence run (HTTP handler)

```bash
pfg persist examples/models.py \
  --handler http-post \
  --handler-config '{"url": "https://api.example.com/orders", "headers": {"Authorization": "Bearer $TOKEN"}}' \
  --include examples.Order \
  --n 100 \
  --batch-size 20 \
  --respect-validators \
  --collection-min-items 1 --collection-max-items 2
```

Swap `http-post` with any custom handler registered under `[persistence.handlers]` when you need Kafka, S3, or database writers.

## Python API equivalents

The same deterministic engine powers the Python helpers. Import what you need from `pydantic_fixturegen.api` and pass the same keyword arguments you would use on the CLI.

```python
from pathlib import Path

from pydantic_fixturegen.api import (
    generate_dataset,
    generate_fixtures,
    generate_json,
    persist_samples,
)
from pydantic_fixturegen.core.path_template import OutputTemplate


json_result = generate_json(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("artifacts/{model}.json"),
    count=10,
    jsonl=True,
    include=["examples.Order"],
    seed=2025,
    collection_min_items=2,
    collection_max_items=4,
    field_hints="defaults",
)

dataset_result = generate_dataset(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("warehouse/{model}-{case_index}.parquet"),
    count=5000,
    format="parquet",
    compression="zstd",
    include=["examples.Order"],
    collection_distribution="max-heavy",
)

fixtures_result = generate_fixtures(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("tests/fixtures/{model}_fixtures.py"),
    style="factory",
    scope="module",
    cases=3,
    include=["examples.Order"],
    collection_min_items=1,
    collection_max_items=2,
)

persistence_run = persist_samples(
    target=Path("examples/models.py"),
    handler="http-post",
    handler_options={"url": "https://api.example.com/orders"},
    count=50,
    batch_size=10,
    include=["examples.Order"],
    collection_min_items=1,
    collection_max_items=2,
)

print(json_result.paths)
print(dataset_result.format, dataset_result.paths)
print(fixtures_result.path)
print(persistence_run.records)
```

- `OutputTemplate` accepts the same placeholders as the CLI.
- `collection_*` and `field_hints` arguments match the CLI flags so you can toggle them per run without editing config files.
- Each result dataclass captures the resolved `ConfigSnapshot`, warnings, and any constraint summaries so you can surface them in logs.

## More inspiration

- Combine the snippets with the [coverage](commands/pfg-coverage.md) and [snapshot](snapshot.md) guides when you want diff-friendly CI stages.
- The [cookbook](cookbook.md) dives deeper into Polyfactory delegation, anonymizer pipelines, and FastAPI smoke tests.
