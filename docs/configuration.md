# Configuration: control determinism, policies, and emitters

> Learn how precedence works, review every config key, and keep CLI/output behaviour consistent across environments.

## Precedence rules

1. CLI arguments.
2. Environment variables prefixed with `PFG_`.
3. `[tool.pydantic_fixturegen]` in `pyproject.toml` or YAML files (`pydantic-fixturegen.yaml` / `.yml`).
4. Built-in defaults defined by `pydantic_fixturegen.core.config.DEFAULT_CONFIG`.

Run `pfg schema config --out schema/config.schema.json` to retrieve the authoritative JSON Schema for editor tooling and validation.

## Dependency baselines

We validate the project against Python 3.10 and 3.14. Floors differ slightly between the two environments; the tables below show the lowest versions that keep the suite green with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

### Python 3.10

| Package  | Minimum | Notes |
| -------- | ------- | ----- |
| `pydantic` | `2.12.4` | Newer floor that still keeps the bundled config schema stable. |
| `faker` | `3.0.0` | 2.x removed locale metadata relied upon in tests. |
| `typer` | `0.12.4` | Verified with Typer `<0.13`; newer majors emit flag deprecation warnings. |
| `click` | `8.1.7` | 8.3+ breaks Typer `count=True` options. |
| `pluggy` | `1.5.0` | Required by `pytest>=8`. |
| `tomli` | `2.0.1` | Only needed on Python <3.11. |

| Extra | Package | Minimum | Notes |
| ----- | ------- | ------- | ----- |
| `[email]` | `email-validator` | `2.0.0` | Pydantic enforces the v2 API. |
| `[payment]` | `pydantic-extra-types` | `2.6.0` | First release verified across 3.10; works with `pydantic==2.12.4`. |
| `[regex]` | `rstr` | `3.2.2` | Avoids Python 3.11+ `re.sre_parse` removals while staying compatible with 3.10. |
| `[orjson]` | `orjson` | `3.11.1` | First release shipping Python 3.14 wheels; also backs down to 3.10. |
| `[hypothesis]` | `hypothesis` | `1.0.0` | Higher versions are fine; the core suite passes down to 1.0. |
| `[watch]` | `watchfiles` | `0.20.0` | Older releases lack Python 3.14 wheels. |
| `[numpy]` | `numpy` | `2.2.6` | Highest release shipping wheels for Python 3.10. |

### Python 3.14

| Package  | Minimum | Notes |
| -------- | ------- | ----- |
| `pydantic` | `2.12.4` | Earliest release with pre-built `cp314` wheels. |
| `faker` | `3.0.0` | Same floor as 3.10. |
| `typer` | `0.12.4` | Works with Typer `<0.13` alongside Click 8.1.x for counter flags. |
| `click` | `8.1.7` | 8.3+ raises errors for `count=True` options. |
| `pluggy` | `1.5.0` | Matches the pytest requirement. |
| `tomli` | _n/a_ | Not required on ≥3.11. |

| Extra | Package | Minimum | Notes |
| ----- | ------- | ------- | ----- |
| `[email]` | `email-validator` | `2.0.0` | Same floor as 3.10. |
| `[payment]` | `pydantic-extra-types` | `2.6.0` | Verified with `pydantic==2.12.4`. |
| `[regex]` | `rstr` | `3.2.2` | Pure-Python distribution works unchanged on 3.14. |
| `[orjson]` | `orjson` | `3.11.1` | First release with Python 3.14 wheels. |
| `[hypothesis]` | `hypothesis` | `1.0.0` | Still valid on 3.14. |
| `[watch]` | `watchfiles` | `0.20.0` | First release shipping Python 3.14-compatible wheels. |
| `[numpy]` | `numpy` | `2.3.2` | Lowest pre-built wheel for Python 3.14 on macOS ARM64. |

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
| `preset`       | `str \| null`                | `null`  | Named preset applied before other config. See [presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/presets.md).      |
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
| `locales`      | `dict[str, str]`             | `{}`    | Pattern-based Faker locale overrides for models or fields.                  |
| `emitters`     | object                       | see below | Configure emitters such as pytest fixtures.                              |
| `json`         | object                       | see below | Configure JSON emitters (shared by JSON/JSONL).                           |
| `paths`        | object                       | see below | Configure filesystem path providers (OS-specific generation). |

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

### Array settings

| Key             | Type          | Default | Description                                                                 |
| --------------- | ------------- | ------- | --------------------------------------------------------------------------- |
| `max_ndim`      | `int`         | `2`     | Maximum number of dimensions for generated NumPy arrays.                    |
| `max_side`      | `int`         | `4`     | Maximum size for any axis; strategies respect both `max_side` and `max_elements`. |
| `max_elements`  | `int`         | `16`    | Hard cap on the total number of elements in generated arrays.              |
| `dtypes`        | `list[str]`   | `["float64"]` | Allowed NumPy dtypes. Values must be accepted by `numpy.dtype`.         |

Install the optional `pydantic-fixturegen[numpy]` extra to enable array providers. When arrays are disabled the configuration is ignored.

### Identifier settings

| Key                   | Type             | Default      | Description                                                                 |
| --------------------- | ---------------- | ------------ | --------------------------------------------------------------------------- |
| `secret_str_length`   | `int`            | `16`         | Default length for generated `SecretStr` values (clamped by field constraints). |
| `secret_bytes_length` | `int`            | `16`         | Default length for generated `SecretBytes` values.                          |
| `url_schemes`         | `list[str]`      | `["https"]` | Allowed URL schemes used by the identifier provider.                        |
| `url_include_path`    | `bool`           | `true`       | Include a deterministic path segment when generating URLs.                  |
| `uuid_version`        | `1 \| 4`         | `4`          | UUID version emitted by the `uuid` provider.                                |

Identifier settings apply to `EmailStr`, `HttpUrl`/`AnyUrl`, secret strings/bytes, payment cards, and IP address fields. Values are chosen via the seeded RNG so fixtures remain reproducible across runs.

> **Note:** Email validation relies on the optional `email` extra. Install it with `pip install "pydantic-fixturegen[email]"` when you need `EmailStr` support.

> **Note:** Payment card fields use the optional `payment` extra backed by `pydantic-extra-types`. Install it with `pip install "pydantic-fixturegen[payment]"` to enable typed `PaymentCardNumber` support.

### Path settings

| Key          | Type                   | Default    | Description |
| ------------ | ---------------------- | ---------- | ----------- |
| `default_os` | `"posix" \| "windows" \| "mac"` | `"posix"` | Baseline OS flavour applied to generated filesystem paths. |
| `models`     | `dict[str, "posix" \| "windows" \| "mac"]` | `{}` | Override the target OS for matching model names (glob patterns). |

Path settings cover `pathlib.Path`, `pydantic.DirectoryPath`, and `pydantic.FilePath` fields so fixtures can mimic Windows drive letters, macOS bundles, or POSIX roots regardless of the host platform.

Example TOML:

```toml
[tool.pydantic_fixturegen.paths]
default_os = "windows"
models = {"app.models.Reporting.*" = "mac", "legacy.schemas.*" = "posix"}
```

The same structure works via YAML or environment variables (`PFG_PATHS__MODELS__legacy.schemas.*=posix`), letting you target specific models without changing the global default.

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

### Locale overrides

Add a `locales` mapping when you need region-specific Faker providers:

```toml
[tool.pydantic_fixturegen.locales]
"app.models.User.*" = "sv_SE"
"app.models.User.email" = "en_GB"
```

- Patterns follow the same rules as `field_policies` (glob or `re:`-prefixed regex).
- Field-level entries override broader model matches; unmatched paths fall back to the global `locale`.
- Configuration loading validates locales by instantiating `Faker(locale)`, so typos raise descriptive errors.

## Environment variable cheatsheet

| Purpose             | Variable                           | Example                                  |
| ------------------- | ---------------------------------- | ---------------------------------------- |
| Seed override       | `PFG_SEED`                         | `export PFG_SEED=1234`                   |
| JSON indent         | `PFG_JSON__INDENT`                 | `export PFG_JSON__INDENT=0`              |
| Enable orjson       | `PFG_JSON__ORJSON`                 | `export PFG_JSON__ORJSON=true`           |
| Fixture style       | `PFG_EMITTERS__PYTEST__STYLE`      | `export PFG_EMITTERS__PYTEST__STYLE=factory` |
| Fixture scope       | `PFG_EMITTERS__PYTEST__SCOPE`      | `export PFG_EMITTERS__PYTEST__SCOPE=session` |
| Field policy update | `PFG_FIELD_POLICIES__*.User.nickname__P_NONE` | `export PFG_FIELD_POLICIES__*.User.nickname__P_NONE=0.2` |
| Array max ndim      | `PFG_ARRAYS__MAX_NDIM`             | `export PFG_ARRAYS__MAX_NDIM=3`          |
| Secret string length | `PFG_IDENTIFIERS__SECRET_STR_LENGTH` | `export PFG_IDENTIFIERS__SECRET_STR_LENGTH=24` |
| Secret bytes length | `PFG_IDENTIFIERS__SECRET_BYTES_LENGTH` | `export PFG_IDENTIFIERS__SECRET_BYTES_LENGTH=32` |
| URL schemes         | `PFG_IDENTIFIERS__URL_SCHEMES`     | `export PFG_IDENTIFIERS__URL_SCHEMES=https,ftp` |
| URL include path    | `PFG_IDENTIFIERS__URL_INCLUDE_PATH` | `export PFG_IDENTIFIERS__URL_INCLUDE_PATH=false` |
| UUID version        | `PFG_IDENTIFIERS__UUID_VERSION`    | `export PFG_IDENTIFIERS__UUID_VERSION=1` |
| Path target        | `PFG_PATHS__DEFAULT_OS`             | `export PFG_PATHS__DEFAULT_OS=windows`           |
| Model path target  | `PFG_PATHS__MODELS__app.models.User` | `export PFG_PATHS__MODELS__app.models.User=mac` |

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

Continue tuning determinism with [presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/presets.md) or lock down reproducibility using [seed freezes](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/seeds.md).
