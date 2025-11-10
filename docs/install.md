# Install: choose the workflow that fits your toolchain

> Install the CLI, enable extras, and confirm the `pfg` entry point is on your PATH.

## pip (recommended)

```bash
python -m pip install --upgrade pip
pip install pydantic-fixturegen
```

- This installs the CLI script `pfg` and pulls core dependencies (`pydantic`, `faker`, `pluggy`, `typer`).
- After installing, verify with `pfg --help`.

## pip with extras

Enable optional capabilities per environment:

```bash
pip install 'pydantic-fixturegen[orjson]'
pip install 'pydantic-fixturegen[regex]'
pip install 'pydantic-fixturegen[hypothesis]'
pip install 'pydantic-fixturegen[watch]'
pip install 'pydantic-fixturegen[fastapi]'
pip install 'pydantic-fixturegen[polyfactory]'
pip install 'pydantic-fixturegen[openapi]'
pip install 'pydantic-fixturegen[dataset]'
pip install 'pydantic-fixturegen[sqlmodel]'
pip install 'pydantic-fixturegen[beanie]'
pip install 'pydantic-fixturegen[seed]'
pip install 'pydantic-fixturegen[all]'
pip install 'pydantic-fixturegen[all-dev]'
```

- `orjson` unlocks faster JSON encoding.
- `regex` installs `rstr` for regex-constrained strings.
- `hypothesis` enables property-based extras in the cookbook.
- `watch` adds filesystem watching via `watchfiles`.
- `fastapi` pulls in FastAPI + Uvicorn so you can use `pfg fastapi smoke` and `pfg fastapi serve`.
- `polyfactory` installs Polyfactory so model discovery can delegate to existing factories and `pfg gen polyfactory` runs immediately.
- `sqlmodel` installs SQLModel + SQLAlchemy for database seeding.
- `beanie` installs Beanie + Motor for MongoDB seeding.
- `seed` bundles both stacks so `pfg gen seed` works out of the box.
- `dataset` installs PyArrow so `pfg gen dataset --format parquet|arrow` works without additional steps.
- `openapi` bundles `datamodel-code-generator` + `PyYAML` so you can ingest JSON Schema/OpenAPI documents directly in `pfg`.
- `all` bundles runtime extras; `all-dev` adds Ruff, mypy, pytest, and pytest-cov.

## Poetry

```bash
poetry add pydantic-fixturegen
poetry run pfg --help
```

- Add extras with `poetry add pydantic-fixturegen[watch]`.
- Use `poetry run pfg ...` inside virtual environments or configure poetry’s `virtualenvs.in-project` setting for local bins.

## Hatch

```toml
# pyproject.toml
[project]
dependencies = ["pydantic-fixturegen"]
```

```bash
hatch run pfg --help
```

- Add extras inside the same dependency list, for example `["pydantic-fixturegen[orjson,watch]"]`.
- Combine with Hatch environments to separate runtime and dev dependencies.

## Extras matrix

| Extra         | Provides                                                                | Ideal for                                     |
| ------------- | ----------------------------------------------------------------------- | --------------------------------------------- |
| `regex`       | `rstr` for regex-based string providers                                 | Models with `Field(regex=...)` constraints    |
| `orjson`      | Fast JSON encoder                                                       | Large JSON/JSONL dumps                        |
| `hypothesis`  | Property-based strategy exporter (`strategy_for`, `pfg gen strategies`) | Generative testing combos                     |
| `watch`       | Live regeneration via `watchfiles`                                      | Watch mode in CI or local loops               |
| `numpy`       | Deterministic NumPy array providers                                     | Models embedding `numpy.ndarray` fields       |
| `fastapi`     | FastAPI + Uvicorn                                                       | Smoke tests and mock servers                  |
| `polyfactory` | Polyfactory                                                             | Delegating to existing `ModelFactory` classes |
| `sqlmodel`    | SQLModel + SQLAlchemy                                                   | SQL database seeding via CLI/fixtures         |
| `beanie`      | Beanie + Motor                                                          | MongoDB seeding                               |
| `seed`        | SQLModel + SQLAlchemy + Beanie + Motor                                  | Enable all seeding workflows                  |
| `dataset`     | PyArrow                                                                 | CSV/Parquet/Arrow dataset emission            |
| `openapi`     | `datamodel-code-generator` + PyYAML                                     | JSON Schema / OpenAPI ingestion workflows     |
| `all`         | Every runtime extra                                                     | One-shot enablement                           |
| `all-dev`     | Runtime extras + mypy, Ruff, pytest, pytest-cov                         | Local development stacks                      |

## Verify the CLI

```bash
pfg --version
pfg schema config --out /tmp/config.schema.json
```

- `pfg --version` prints the installed version and resolves the entry point declared under `[project.scripts]`.
- `pfg schema config` confirms Typer loads dynamic subcommands correctly.

You are ready to follow the [Quickstart](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/quickstart.md) or dig into configuration defaults.
