# Documentation index

> Understand the value proposition, install the CLI, and drill into the workflow you need.

## Why pydantic-fixturegen?

- **Determinism everywhere** — cascaded seeds across `random`, Faker, NumPy, and PyArrow plus optional freeze files keep JSON, datasets, fixtures, FastAPI smoke tests, and anonymized payloads byte-for-byte identical.
- **Guardrails built in** — sandboxed discovery, `pfg diff`, `pfg doctor`, `pfg snapshot`, lockfiles, and coverage manifests let CI block regressions without custom glue code.
- **Extensible engine** — Pluggy hooks, Polyfactory delegation, schema ingestion, dataset emitters, anonymizer, Hypothesis strategies, SQLModel/Beanie seeders, and FastAPI tooling reuse the same generation plan across APIs, tests, and data pipelines.
- **Dataclasses + TypedDicts** — the same configuration/preset system now works for stdlib `@dataclass` types and `typing.TypedDict` alongside native Pydantic models (attrs/msgspec under active discussion).

If you are comparing tools, start with the [Alternatives & migration guides](alternatives.md) to see head-to-head features, Polyfactory/Pydantic-Factories migration steps, and real-world case studies.

## Start here

1. **Install + verify** — follow the [Install guide](install.md) to pick pip/Poetry/Hatch and enable extras like `fastapi`, `openapi`, `polyfactory`, `dataset`, or `seed`.
2. **Hands-on tour** — run through the [Quickstart](quickstart.md) to discover models, emit JSON/datasets/fixtures, diff artifacts, and capture deterministic snapshots.
3. **Configure once** — keep the [Configuration reference](configuration.md) open to centralise seeds, presets, heuristic policies, and emitter defaults. Refer back to [Concepts](concepts.md) when you want background on sandboxing, determinism, or hook design.

Already familiar with the basics? Jump to the section that matches your task.

### Day-to-day workflows

- [CLI reference](cli.md) — command-by-command coverage (`list`, `gen`, datasets, fixtures, seeders, anonymize, FastAPI, snapshot, lock, verify, doctor, schema, plugin scaffolding).
- [Cookbook](cookbook.md) — apply repeatable recipes for diffing artifacts, streaming datasets, toggling presets, seeding databases, or wiring Polyfactory delegation.
- [Testing helpers](testing.md) — pytest snapshot fixture, CLI snapshot commands (`pfg snapshot verify/write`), and CI/linting tips.
- [Doctor & diagnostics](doctor.md) — interpret coverage reports, enforce `--fail-on-gaps`, and integrate lockfiles.
- [Features at a glance](features.md) — skim capabilities (discovery, generation, emitters, privacy) with links to deep dives.

### Emitters & integrations

- [Discovery guide](discovery.md) — AST vs safe-import, sandbox caps, schema ingestion, OpenAPI fan-out.
- [Emitters](emitters.md) — JSON/JSONL, datasets (CSV/Parquet/Arrow), pytest fixtures, schema emitters, anonymizer workflows, and FastAPI smoke/mock commands.
- [Providers](providers.md) & [Strategies](strategies.md) — extend providers, heuristics, and Hypothesis exporters.
- [Seeds](seeds.md) & [Presets](presets.md) — freeze seeds, manage optional probabilities, compose privacy profiles.
- [Output paths](output-paths.md) — templated destinations, sharding, compression rules.
- [Logging](logging.md) — JSON logs, event schemas, verbosity toggles, CI piping.

### Reference material

- [API reference](api.md) — call `generate_json`, `generate_dataset`, `generate_fixtures`, `generate_schema`, and anonymizer helpers from Python, complete with parameter tables and result fields.
- [Security](security.md) — sandbox boundaries, exit codes, safe-import behaviour, supply-chain considerations.
- [Troubleshooting](troubleshooting.md) — error taxonomy, watch mode fixes, Typer proxy gotchas.
- [VS Code integration](vscode.md) — ready-made tasks and problem matchers for editor-driven workflows.
- [Architecture](architecture.md) — visualise the generation pipeline, hook order, and configuration precedence.

All docs stay in second-person so you can copy/paste commands without mental translation. If something feels missing, open an issue—the docs ship from the same repo as the CLI.
