# `pfg list`

## Capabilities
`pfg list` discovers Pydantic models inside a Python module without generating artifacts. It runs the same discovery pipeline used by the generators (AST + safe-import hybrids) so you can verify what will actually be emitted, surface sandbox warnings, and feed the and include/exclude globs you plan to reuse later.

## Typical use cases
- Smoke-test a new module before running heavy generators.
- Record the exact fully-qualified names to pin in `--include`/`--exclude` or config files.
- Compare AST-only vs hybrid discovery when imports have side effects.
- Validate that safe-import memory and timeout guards suit CI sandboxes.

## Inputs & outputs
- **Input**: path to a Python module (`.py`) containing Pydantic v2 models. The command refuses to traverse packages or directories.
- **Output**: each discovered model printed as `<module.qualname> [discovery_method]`. Warnings appear on stderr with `warning:` prefix. On failure the command exits with a non-zero status and, when `--json-errors` is set globally, emits structured JSON diagnostics.

## Flag reference
**Discovery control**
- `--include/-i`, `--exclude/-e`: comma-separated glob patterns (supports `*`, `?`, and dotted module names). Patterns run against fully-qualified names.
- `--public-only`: only emit models that appear in `__all__` or that do not start with `_`.
- `--ast`: run pure-AST discovery (no imports executed). Great when models import optional dependencies.
- `--hybrid`: run AST first, then fall back to safe-import for unresolved symbols. Mutually exclusive with `--ast`.
- `--timeout`: wall-clock timeout (seconds) for the safe-import subprocess (default 5.0s).
- `--memory-limit-mb`: RSS cap for safe-import (default 256MB). Bump this for very large dependency graphs.

**Diagnostics**
- `--json-errors`: inherit from the global root; when set, errors surface as JSON payloads with codes such as `unsafe_import`.

## Example workflows
### AST-only discovery
```bash
pfg list ./app/models.py --ast --include app.schemas.*
```
Prints only models inside `app.schemas` without touching imports.

**Sample output**
```text
app.schemas.User [ast]
app.schemas.Address [ast]
```

### Hybrid discovery with tighter guardrails
```bash
pfg list ./app/models.py --hybrid --timeout 2 --memory-limit-mb 128 --public-only
```
Runs a fast hybrid scan suited for CI and surfaces warnings if imports exceed the sandbox budget.

**Sample output**
```text
warning: import sandbox exceeded 120 MB; retrying with AST fallbacks
app.models.User [hybrid]
app.models.Order [hybrid]
```

## Operational notes
- Exit code `0` indicates at least one model was listed (even when warnings were emitted). A missing file or empty result triggers `DiscoveryError` → non-zero exit.
- Safe-import runs in a sandboxed child process; if the subprocess touched the network or disk unexpectedly you will see `UnsafeImportError` text.
- `pfg list` is the default command: running `pfg` with no subcommand implicitly calls it after configuring logging.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-list)
- [Discovery pipeline](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/discovery.md)
- [Security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md#safe-import)
