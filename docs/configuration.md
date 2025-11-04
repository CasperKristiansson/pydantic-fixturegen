# Configuration: control determinism, policies, and emitters

> Learn how precedence works, review every config key, and keep CLI/output behaviour consistent across environments.

## Precedence rules

1. CLI arguments.
2. Environment variables prefixed with `PFG_`.
3. `[tool.pydantic_fixturegen]` in `pyproject.toml` or YAML files (`pydantic-fixturegen.yaml` / `.yml`).
4. Built-in defaults defined by `pydantic_fixturegen.core.config.DEFAULT_CONFIG`.

Run `pfg schema config --out schema/config.schema.json` to retrieve the authoritative JSON Schema for editor tooling and validation.

## Configuration sources

- **CLI flags**: every `pfg` command accepts options that override lower layers; e.g., `--seed`, `--indent`, `--style`.
- **Environment**: mirror nested keys with double underscores. Example: `export PFG_EMITTERS__PYTEST__STYLE=factory`.
- **Project files**: use either `[tool.pydantic_fixturegen]` in `pyproject.toml` or a YAML config file. Run `pfg init` to scaffold both.
- **Freeze file**: `.pfg-seeds.json` is managed automatically when you enable `--freeze-seeds`.

## Quick-start snippet

```toml
[tool.pydantic_fixturegen]
seed = 42
locale = "en_US"
union_policy = "weighted"
enum_policy = "random"

[tool.pydantic_fixturegen.json]
indent = 2
orjson = false

[tool.pydantic_fixturegen.emitters.pytest]
style = "functions"
scope = "module"
```

`pfg init` generates a similar block and can also create `pydantic-fixturegen.yaml` when you pass `--yaml`.

## Top-level keys

| Key            | Type                         | Default | Description                                                                 |
| -------------- | ---------------------------- | ------- | --------------------------------------------------------------------------- |
| `preset`       | `str \| null`                | `null`  | Named preset applied before other config. See [presets](./presets.md).      |
| `seed`         | `int \| str \| null`         | `null`  | Global seed. Provide an explicit value for reproducible outputs.            |
| `locale`       | `str`                        | `en_US` | Faker locale used when generating data.                                     |
| `include`      | `list[str]`                  | `[]`    | Glob patterns of fully-qualified model names to include by default.         |
| `exclude`      | `list[str]`                  | `[]`    | Glob patterns to exclude.                                                   |
| `p_none`       | `float \| null`              | `null`  | Baseline probability of returning `None` for optional fields.               |
| `union_policy` | `first \| random \| weighted` | `first` | Strategy for selecting branches of `typing.Union`.                          |
| `enum_policy`  | `first \| random`            | `first` | Strategy for selecting enum members.                                        |
| `now`          | `datetime \| null`           | `null`  | Anchor timestamp used for temporal values.                                  |
| `overrides`    | `dict[str, dict[str, Any]]`  | `{}`    | Per-model overrides keyed by fully-qualified model name.                    |
| `field_policies` | `dict[str, FieldPolicy]`   | `{}`    | Pattern-based overrides for specific fields.                                |
| `emitters`     | object                       | see below | Configure emitters such as pytest fixtures.                              |
| `json`         | object                       | see below | Configure JSON emitters (shared by JSON/JSONL).                           |

### JSON settings

| Key           | Type    | Default | Description                                      |
| ------------- | ------- | ------- | ------------------------------------------------ |
| `indent`      | `int`   | `2`     | Indentation level. Set `0` for compact output.   |
| `orjson`      | `bool`  | `false` | Use `orjson` if installed for faster encoding.   |

These values apply to both `pfg gen json` and JSONL emission. CLI flags `--indent` and `--orjson/--no-orjson` override them.

### Pytest emitter settings

| Key     | Type                       | Default   | Description                                     |
| ------- | -------------------------- | --------- | ----------------------------------------------- |
| `style` | `functions \| factory \| class` | `functions` | Fixture style structure.                        |
| `scope` | `function \| module \| session` | `function`  | Default fixture scope.                          |

Change these values to adjust generated module ergonomics. CLI flags `--style` and `--scope` override them.

### Field policy schemas

`field_policies` accepts nested options that map patterns to policy tweaks.

```toml
[tool.pydantic_fixturegen.field_policies."*.User.nickname"]
p_none = 0.25
union_policy = "random"
enum_policy = "random"
```

- Patterns accept glob-style wildcards or regex (enable `regex` extra).
- Values match the schema defined under `$defs.FieldPolicyOptionsSchema`.
- Use `pfg gen explain` to confirm the overrides take effect.

## Environment variable cheatsheet

| Purpose             | Variable                           | Example                                  |
| ------------------- | ---------------------------------- | ---------------------------------------- |
| Seed override       | `PFG_SEED`                         | `export PFG_SEED=1234`                   |
| JSON indent         | `PFG_JSON__INDENT`                 | `export PFG_JSON__INDENT=0`              |
| Enable orjson       | `PFG_JSON__ORJSON`                 | `export PFG_JSON__ORJSON=true`           |
| Fixture style       | `PFG_EMITTERS__PYTEST__STYLE`      | `export PFG_EMITTERS__PYTEST__STYLE=factory` |
| Fixture scope       | `PFG_EMITTERS__PYTEST__SCOPE`      | `export PFG_EMITTERS__PYTEST__SCOPE=session` |
| Field policy update | `PFG_FIELD_POLICIES__*.User.nickname__P_NONE` | `export PFG_FIELD_POLICIES__*.User.nickname__P_NONE=0.2` |

Environment values treat `true/false/1/0` as booleans, respect floats for `p_none`, and parse nested segments via double underscores.

## YAML configuration

`pfg init --yaml` produces `pydantic-fixturegen.yaml`. The schema mirrors the TOML structure:

```yaml
preset: boundary
seed: 42
json:
  indent: 2
  orjson: false
emitters:
  pytest:
    style: factory
    scope: module
```

Store YAML alongside your project root or pass `--yaml-path` explicitly to CLI commands.

## Validating configuration

- `pfg check <target>` validates discovery, configuration, and emitter destinations without writing files.
- `pfg schema config` prints the JSON Schema so your editor can autocomplete keys.
- Invalid keys raise `ConfigError` with clear messages indicating the source (CLI, env, file).

Continue tuning determinism with [presets](./presets.md) or lock down reproducibility using [seed freezes](./seeds.md).
