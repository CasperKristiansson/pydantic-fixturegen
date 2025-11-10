# Troubleshooting: unblock generation quickly

> Decode error codes, address sandbox issues, and keep CI green.

## Error taxonomy

| Code | Meaning                                   | Fix                                                             |
| ---- | ----------------------------------------- | --------------------------------------------------------------- |
| `0`  | Success                                   | No action needed.                                               |
| `20` | Structured discovery/config error         | Inspect JSON payload (`--json-errors`) for `kind` and `detail`. |
| `40` | Sandbox timeout                           | Increase `--timeout` or optimise imports.                       |
| `41` | Sandbox memory limit (platform dependent) | Raise `--memory-limit-mb` or refactor heavy imports.            |
| `2`  | `pfg doctor --fail-on-gaps` threshold hit | Add providers or relax the fail threshold.                      |

## Common issues

- **“No models discovered.”** — Check the path points to a file, not a package. Use `--hybrid` for dynamic registration.
- **Sandbox blocked a write or network call.** — Place outputs beneath the working directory and remove network access from model imports.
- **JSON diffs differ between machines.** — Ensure all environments pin the same seed (CLI/env/config) and enable `--freeze-seeds`.
- **Optional fields too dense/sparse.** — Adjust `p_none` via CLI/env/config or set field-level policies.
- **Watch mode not triggering.** — Install the `watch` extra and verify edits happen under the project root. Tune `--watch-debounce`.
- **`ValueError: No provider registered`** — Add a custom provider or update dependencies (for example install `regex` extra for constrained strings).
- **`seed_freeze_stale` warnings.** — Accept new digests by committing the updated `.pfg-seeds.json` or rerun with the previous model definition.

## Debug checklist

1. Run `pfg list --json-errors` to confirm discovery works.
2. Execute `pfg doctor --fail-on-gaps 0` to catch coverage issues.
3. Enable `--log-json` and capture events for review.
4. Drop into `pfg gen explain --tree` to inspect provider choices.
5. Rebuild with `--seed` and compare outputs via `pfg diff`.

Escalate to [security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md) if sandbox violations persist or to [support channels](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/README.md#community) when you need assistance.
