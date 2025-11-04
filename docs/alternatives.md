# Alternatives: choose the right fixture tool

> Compare pydantic-fixturegen with common approaches so you can justify the switch.

| Tooling                     | Determinism                                        | Plugin model                           | Sandboxing            | CLI coverage                          | Best fit                                                |
| --------------------------- | -------------------------------------------------- | --------------------------------------- | --------------------- | ------------------------------------- | ------------------------------------------------------- |
| **pydantic-fixturegen**     | Strong: cascaded seeds across `random`/Faker/NumPy | Pluggy hooks (`pfg_register_providers`, `pfg_modify_strategy`, `pfg_emit_artifact`) | Yes (network, FS jail, caps) | Broad (`list`, `gen`, `diff`, `check`, `doctor`, `explain`) | Teams needing deterministic Pydantic fixtures and JSON artifacts |
| Hand-written fixtures       | Manual discipline required                         | None                                    | None                  | None                                  | Small codebases with few models                         |
| `factory_boy`               | Optional seeding                                   | Class-based factories                   | None                  | N/A                                   | ORM-backed object factories                             |
| `hypothesis.extra.pydantic` | Generative, not fixed by default                   | Strategy composition                    | None                  | N/A                                   | Property-based exploration                              |
| Custom scripts              | Depends on implementation                          | Ad hoc                                  | Rare                  | Rare                                  | One-off data dumps without reusable tooling             |

When you need deterministic JSON/JSONL, pytest fixtures, and schema artefacts with a secure sandbox, pydantic-fixturegen keeps everything in one CLI. Use other tools when you prioritise interactive data exploration over reproducibility.
