# Discovery: find models safely

> Choose the right discovery mode and tune sandbox limits for your project.

## Discovery modes

- **Import (default)**: Runs modules inside the safe-import sandbox to resolve dynamic models. Fallback to AST when imports fail.
- **`--ast`**: Parses source code without executing imports. Use this for untrusted code or when imports have side effects.
- **`--hybrid`**: Combines AST and safe-import results for maximum coverage.

Invoke discovery via `pfg list`, `pfg gen *`, `pfg diff`, `pfg check`, and `pfg doctor`.

## Filtering models

```bash
pfg list ./models.py --include app.models.User --exclude "*.Internal*" --public-only
```

- `--include` and `--exclude` accept comma-separated glob patterns.
- `--public-only` respects `__all__` and ignores private models.
- Patterns also apply to generation commands, ensuring only desired models receive artifacts.

## Sandbox controls

```bash
pfg list ./models.py --timeout 10 --memory-limit-mb 512 --json-errors
```

- `--timeout` sets safe-import execution timeout (seconds). Exceeding it raises exit code `40`.
- `--memory-limit-mb` caps sandbox memory. Increase it when models pull large dependencies.
- `--json-errors` emits structured error payloads with code `20` for easy parsing.

## Handling warnings

- Discovery prints warnings for risky imports, missing providers, or skipped models. Capture them by redirecting stderr.
- `pfg doctor` aggregates warnings into structured reports; run it when new models appear.

## Tips

- Run `pfg list --ast` during code review to ensure models register even without installing optional extras.
- Use hybrid mode when you rely on runtime registration but still want AST coverage.
- When sandbox violations occur (attempted network access, forbidden writes), review [security](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/security.md) to understand the guardrails.
- Combine discovery filters with `pfg gen` to avoid generating fixtures for helper or internal models.
