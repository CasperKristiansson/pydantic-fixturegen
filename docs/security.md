# Security: sandbox and safe-import guarantees

> Run untrusted models with network, filesystem, and resource guarantees.

## Safe-import sandbox

- Executes discovery and generation inside a subprocess with restricted permissions.
- Blocks socket creation by monkey-patching `socket.socket` and related APIs.
- Scrubs proxy environment variables (`NO_PROXY=*`, `HTTP(S)_PROXY` removed) and sets `PYTHONSAFEPATH=1`.
- Redirects HOME and temporary directories into a sandbox-local path.
- Denies writes outside the working directory by overriding `open`, `io.open`, and `os.open`.
- Applies memory caps via `resource.RLIMIT_AS` and `resource.RLIMIT_DATA` when available.
- Times out imports and emits exit code `40` when the timeout is exceeded. Configure via `--timeout`.

## Discovery modes

- `--ast` keeps imports disabled and parses source directly.
- Default mode combines AST pre-flight with sandboxed imports to resolve dynamic attributes safely.
- `--hybrid` ensures both methods run and merges results.

## Hardened commands

- `pfg list`, `pfg gen *`, `pfg diff`, and `pfg check` all rely on the sandbox from the same core implementation.
- `pfg doctor` surfaces sandbox breaches, risky imports, and coverage gaps; use `--fail-on-gaps` to fail CI.
- Atomic IO protects JSON, schema, and fixture outputs: a generation failure leaves previous files untouched.

## Operating the sandbox

- Adjust timeouts with `--timeout` and memory limits with `--memory-limit-mb` on `pfg list`.
- When debugging blocked writes, move your output path inside the project root or use templates that avoid `../`.
- Sandbox exit codes: `0` success, `20` structured discovery errors, `40` timeout, others bubble up from Python exceptions.

Pair this with [doctor diagnostics](./doctor.md) for a full audit trail and record structured logs via [logging](./logging.md).
