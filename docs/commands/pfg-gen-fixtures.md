# `pfg gen fixtures`

## Capabilities
`pfg gen fixtures` emits pytest modules that wrap deterministic generator calls. It respects your preferred fixture style (`functions`, `factory`, or `class`), scope, parametrisation count, and return type. Every run embeds metadata (seed, digest, preset, style) so diffs clearly show why a fixture changed.

## Typical use cases
- Create reusable pytest fixtures for each model with consistent seeds.
- Generate fixture modules that you check into `tests/fixtures/` alongside unit tests.
- Emit temporary fixtures in watch mode while developing new models.
- Share deterministic bundles (`--with-related`) that keep cross-model references intact.

## Inputs & outputs
- **Target**: Python module containing models.
- **Output**: Python file resolved from `--out`. Templates are supported (`tests/fixtures/{model}_fixtures.py`).
- **Result metadata**: command prints the generated path and logs `style`, `scope`, `return_type`, and cases.

## Flag reference
**Fixture layout**
- `--style`: fixture signature style. Defaults to config (`functions`).
- `--scope`: pytest scope (`function`, `module`, `session`). Defaults to config.
- `--cases`: number of parametrized cases per fixture (default 1). Each case receives deterministic seeds.
- `--return-type`: `model` (default) or `dict`.
- `--p-none`: override probability of emitting `None` for optional fields.

**Discovery & selection**
- `--include/-i`, `--exclude/-e`: fully-qualified glob filters.

**Determinism + privacy**
- `--seed`, `--preset`, `--profile`, `--now`, `--rng-mode` identical to JSON command.
- `--freeze-seeds`, `--freeze-seeds-file`: persist per-model seeds so fixture diffs only change when inputs do.
- `--field-hints`: honor `Field` defaults/examples before providers (modes mirror `pfg gen json`).

**Collection controls**
- `--collection-min-items` / `--collection-max-items`: drive how many entries lists/sets/tuples/mappings contain inside the emitted fixture payloads (clamped by schema constraints). Helpful when you want richer factory cases without editing config files.
- `--collection-distribution`: bias fixture collections toward lower, upper, or even spans.

**Relations + depth**
- `--link` and `--with-related`: declare relationships and co-generate related fixtures (helpful when you want `Order` fixtures to bundle `User` instances in the same module).
- `--max-depth`, `--on-cycle`: control recursion for nested models.

**Quality controls**
- `--respect-validators`, `--validator-max-retries`: enforce validator success before writing fixtures.
- `-O/--override`: inline per-field override JSON (identical semantics to `[tool.pydantic_fixturegen.overrides]`).

**Watch mode**
- `--watch` plus `--watch-debounce` (default 0.5s) rerun fixture generation when any tracked file changes. The watcher monitors the target module tree, config files, and the fixture output path.

## Example workflows
### Session-scoped factory fixtures with related models
```bash
pfg gen fixtures ./app/models.py \
  --out tests/fixtures/{model}_fixtures.py \
  --style factory --scope session --cases 4 --return-type dict \
  --include app.models.User,app.models.Order \
  --with-related app.models.Address \
  --seed 11 --preset boundary --profile pii-safe
```
Writes per-model fixture modules where each case bundles deterministic User/Order/Address data.

**Generated fixture excerpt (`tests/fixtures/app.models.User_fixtures.py`)**
```python
@pytest.fixture(scope="session")
def user_factory_case_1():
    return {
        "User": {
            "id": UUID("6ad0ab66-6c07-42c0-9e86-5b9292e70ac4"),
            "email": "avery@example.org",
            "profile": {"timezone": "UTC", "marketing_opt_in": False},
        },
        "Address": {
            "street": "826 Boundary Loop",
            "city": "Deterministic",
            "postal_code": "00011",
        },
    }
```

**Sample output**
```text
[fixtures_written] path=tests/fixtures/app.models.User_fixtures.py cases=4 style=factory return=dict
[fixtures_written] path=tests/fixtures/app.models.Order_fixtures.py cases=4 style=factory return=dict
metadata:
  seed: 11
  profile: pii-safe
  related: ['app.models.Address']
```

### Additional examples

```bash
# Session-scoped fixtures for dataclasses/TypedDicts with dense collections
pfg gen fixtures examples/models.py \
  --include examples.Order \
  --out tests/fixtures/{model}_fixtures.py \
  --style factory --scope session --cases 4 \
  --collection-min-items 1 --collection-max-items 3

# Function-style fixtures that return dicts (easier to JSON serialize)
pfg gen fixtures ./models.py \
  --include app.schemas.User \
  --style functions --return-type dict --cases 2
```

Python API equivalent:

```python
from pathlib import Path
from pydantic_fixturegen.api import generate_fixtures
from pydantic_fixturegen.core.path_template import OutputTemplate

generate_fixtures(
    target=Path("examples/models.py"),
    output_template=OutputTemplate("tests/fixtures/{model}_fixtures.py"),
    style="factory",
    scope="module",
    cases=3,
    include=["examples.Order"],
    collection_min_items=1,
    collection_max_items=2,
)
```

See [docs/examples.md](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/examples.md#cli-flows) for combined fixture + persistence pipelines.

### Watch mode for rapid iteration
```bash
pfg gen fixtures ./app/models.py --out tests/fixtures/users.py --watch --include app.models.User
```
Keeps regenerating `users.py` whenever the model file or config changes.

**Sample output**
```text
[watch] tracking=/repo/app/models.py,/repo/tests/fixtures/users.py
Initial run succeeded: tests/fixtures/users.py
<ctrl-c to exit>
```

## Operational notes
- Generated modules include banner metadata so code review can confirm the random seed, preset, and CLI version that produced them.
- Exit code mirrors Typer defaults; invalid style/scope values raise `BadParameter` before touching disk.
- When `--with-related` is present, each fixture returns a mapping keyed by model name so tests can destructure related instances easily.
- To keep diffs readable, commit with `black`-compatible formatting (fixturegen already emits formatted code).

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-gen-fixtures)
- [Emitters: pytest](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/emitters.md#pytest-fixtures)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
- [Seeds & presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md)
