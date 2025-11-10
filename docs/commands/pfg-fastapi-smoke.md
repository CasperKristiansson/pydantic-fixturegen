# `pfg fastapi smoke`

## Capabilities
`pfg fastapi smoke` introspects a FastAPI app, generates deterministic request/response payloads, and writes a pytest module with one smoke test per route. Each test makes a live request using `TestClient`, asserts a 2xx response, and validates the payload with the same fixturegen generator the rest of the CLI uses.

## Typical use cases
- Guard every route with a deterministic smoke test without writing repetitive code.
- Generate a baseline test suite for new services before writing focused unit tests.
- Share seed-locked smoke suites across teams so failures are easy to debug.

## Inputs & outputs
- **Target**: FastAPI import path (`module:attr`, for example `app.main:app`). Required.
- **Output**: `--out` (default `tests/test_fastapi_smoke.py`). The command overwrites the file with the freshly generated suite.

## Flag reference
- `--out/-o`: pytest module destination.
- `--seed`: override the deterministic seed embedded in the generated suite. When omitted, tests call fixturegen with the default seed from config.
- `--dependency-override original=override`: repeatable option that injects FastAPI dependency overrides (resolves dotted or colon-separated paths). Essential for bypassing authentication, rate limiters, etc.

## Example workflows
### Generate smoke tests with dependency stubs
```bash
pfg fastapi smoke app.main:app \
  --out tests/test_fastapi_smoke.py \
  --seed 11 \
  --dependency-override "app.dependencies.get_current_user=fakes.allow_all"
```
Writes one pytest function per route, overriding `get_current_user` so auth checks pass.

**Sample output**
```text
Smoke tests written to tests/test_fastapi_smoke.py
Routes covered: 12
Dependency overrides: ['app.dependencies.get_current_user=fakes.allow_all']
```

**Excerpt from generated `tests/test_fastapi_smoke.py`**
```python
def test_get_users_returns_200(smoke_client):
    payload = generate_payload("GET /users")
    response = smoke_client.get("/users", params=payload.query, headers=payload.headers)
    assert response.status_code == 200
    assert response.json() == payload.expected
```

### Separate smoke suites per router

```bash
pfg fastapi smoke app.api.users:router \
  --out tests/smoke/test_users_api.py \
  --seed 5 \
  --dependency-override "app.dependencies.get_db=fakes.memory_db"
```

Generates a focused smoke module for the `users` router while overriding the DB dependency with an in-memory stub.


## Operational notes
- Requires the `fastapi` extra (`pip install pydantic-fixturegen[fastapi]`).
- Routes are grouped by HTTP method; each smoke test exercises validation via fixturegen so payloads stay reproducible.
- Custom overrides are evaluated via import, so ensure the override target is importable (module path or `pkg.module:attr`).
- Exit codes follow Typer defaults; missing app attributes trigger `DiscoveryError` with helpful hints.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-fastapi)
- [FastAPI cookbook entries](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cookbook.md#fastapi)
- [Testing helpers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/testing.md)
