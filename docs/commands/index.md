# Command Guides

This section expands on the high-level [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md) by dedicating a deep dive to every `pfg` command and subcommand. Each guide covers:

- What the command does and when to choose it.
- Required inputs, emitted artifacts, and deterministic controls.
- Flag-by-flag behavior grouped by theme.
- Worked examples that mirror common workflows or CI pipelines.
- Operational tips (exit codes, logging, integration hooks) plus related docs.

Browse the guides:

| Command                           | Guide                                                              |
| --------------------------------- | ------------------------------------------------------------------ |
| `pfg list`                        | [List models](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-list.md)                                       |
| `pfg gen json`                    | [Generate JSON payloads](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-json.md)                        |
| `pfg gen dataset`                 | [Generate CSV/Parquet/Arrow datasets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-dataset.md)        |
| `pfg gen fixtures`                | [Emit pytest fixtures](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-fixtures.md)                      |
| `pfg gen schema`                  | [Write JSON Schema files](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-schema.md)                     |
| `pfg gen openapi`                 | [Generate JSON from OpenAPI components](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-openapi.md)      |
| `pfg gen examples`                | [Inject OpenAPI examples](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-examples.md)                   |
| `pfg gen strategies`              | [Export Hypothesis strategies](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-strategies.md)            |
| `pfg gen polyfactory`             | [Scaffold Polyfactory delegates](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-polyfactory.md)         |
| `pfg gen seed sqlmodel`           | [Seed SQLModel / SQLAlchemy databases](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-seed-sqlmodel.md) |
| `pfg gen seed beanie`             | [Seed Beanie / MongoDB databases](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-seed-beanie.md)        |
| `pfg gen explain` / `pfg explain` | [Inspect generation strategies](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-gen-explain.md)              |
| `pfg anonymize`                   | [Deterministic payload anonymizer](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-anonymize.md)             |
| `pfg fastapi smoke`               | [FastAPI smoke-test generator](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-fastapi-smoke.md)             |
| `pfg fastapi serve`               | [Deterministic FastAPI mock server](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-fastapi-serve.md)        |
| `pfg diff`                        | [Diff regenerated artifacts](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-diff.md)                        |
| `pfg check`                       | [Validate configuration + emitters](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-check.md)                |
| `pfg doctor`                      | [Coverage & provider auditor](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-doctor.md)                     |
| `pfg init`                        | [Project scaffolding](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-init.md)                               |
| `pfg plugin`                      | [Provider plugin scaffolding](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-plugin.md)                     |
| `pfg lock`                        | [Write coverage lockfiles](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-lock.md)                          |
| `pfg verify`                      | [Verify coverage lockfiles](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-verify.md)                       |
| `pfg snapshot verify`             | [Diff stored snapshots](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-verify.md)                  |
| `pfg snapshot write`              | [Refresh stored snapshots](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-snapshot-write.md)                |
| `pfg schema config`               | [Emit configuration JSON Schema](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/commands/pfg-schema-config.md)           |

Each guide cross-links to the rest of the documentation set so you can jump between configuration, provider internals, and testing references without losing context.
