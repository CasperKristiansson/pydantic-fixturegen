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

| Package    | Minimum  | Notes                                                                     |
| ---------- | -------- | ------------------------------------------------------------------------- |
| `pydantic` | `2.12.4` | Newer floor that still keeps the bundled config schema stable.            |
| `faker`    | `3.0.0`  | 2.x removed locale metadata relied upon in tests.                         |
| `typer`    | `0.12.4` | Verified with Typer `<0.13`; newer majors emit flag deprecation warnings. |
| `click`    | `8.1.7`  | 8.3+ breaks Typer `count=True` options.                                   |
| `pluggy`   | `1.5.0`  | Required by `pytest>=8`.                                                  |
| `tomli`    | `2.0.1`  | Only needed on Python <3.11.                                              |

| Extra          | Package                | Minimum  | Notes                                                                           |
| -------------- | ---------------------- | -------- | ------------------------------------------------------------------------------- |
| `[email]`      | `email-validator`      | `2.0.0`  | Pydantic enforces the v2 API.                                                   |
| `[payment]`    | `pydantic-extra-types` | `2.6.0`  | First release verified across 3.10; works with `pydantic==2.12.4`.              |
| `[regex]`      | `rstr`                 | `3.2.2`  | Avoids Python 3.11+ `re.sre_parse` removals while staying compatible with 3.10. |
| `[orjson]`     | `orjson`               | `3.11.1` | First release shipping Python 3.14 wheels; also backs down to 3.10.             |
| `[hypothesis]` | `hypothesis`           | `1.0.0`  | Higher versions are fine; the core suite passes down to 1.0.                    |
| `[watch]`      | `watchfiles`           | `0.20.0` | Older releases lack Python 3.14 wheels.                                         |
| `[numpy]`      | `numpy`                | `2.2.6`  | Highest release shipping wheels for Python 3.10.                                |

### Python 3.14

| Package    | Minimum  | Notes                                                             |
| ---------- | -------- | ----------------------------------------------------------------- |
| `pydantic` | `2.12.4` | Earliest release with pre-built `cp314` wheels.                   |
| `faker`    | `3.0.0`  | Same floor as 3.10.                                               |
| `typer`    | `0.12.4` | Works with Typer `<0.13` alongside Click 8.1.x for counter flags. |
| `click`    | `8.1.7`  | 8.3+ raises errors for `count=True` options.                      |
| `pluggy`   | `1.5.0`  | Matches the pytest requirement.                                   |
| `tomli`    | _n/a_    | Not required on ≥3.11.                                            |

| Extra          | Package                | Minimum  | Notes                                                  |
| -------------- | ---------------------- | -------- | ------------------------------------------------------ |
| `[email]`      | `email-validator`      | `2.0.0`  | Same floor as 3.10.                                    |
| `[payment]`    | `pydantic-extra-types` | `2.6.0`  | Verified with `pydantic==2.12.4`.                      |
| `[regex]`      | `rstr`                 | `3.2.2`  | Pure-Python distribution works unchanged on 3.14.      |
| `[orjson]`     | `orjson`               | `3.11.1` | First release with Python 3.14 wheels.                 |
| `[hypothesis]` | `hypothesis`           | `1.0.0`  | Still valid on 3.14.                                   |
| `[watch]`      | `watchfiles`           | `0.20.0` | First release shipping Python 3.14-compatible wheels.  |
| `[numpy]`      | `numpy`                | `2.3.2`  | Lowest pre-built wheel for Python 3.14 on macOS ARM64. |

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

| Key                     | Type                        | Default    | Description                                                                                                                                   |
| ----------------------- | --------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `preset`                | `str \ null`                | `null`     | Named preset applied before other config. See [presets](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/presets.md). |
| `profile`               | `str \ null`                | `null`     | Profile applied ahead of other settings (`pii-safe`, `realistic`, `edge`, `adversarial`).                                                     |
| `seed`                  | `int \ str \ null`          | `null`     | Global seed. Provide an explicit value for reproducible outputs.                                                                              |
| `locale`                | `str`                       | `en_US`    | Faker locale used when generating data.                                                                                                       |
| `include`               | `list[str]`                 | `[]`       | Glob patterns of fully-qualified model names to include by default.                                                                           |
| `exclude`               | `list[str]`                 | `[]`       | Glob patterns to exclude.                                                                                                                     |
| `p_none`                | `float \ null`              | `null`     | Baseline probability of returning `None` for optional fields.                                                                                 |
| `union_policy`          | `first \ random \ weighted` | `first`    | Strategy for selecting branches of `typing.Union`.                                                                                            |
| `enum_policy`           | `first \ random`            | `first`    | Strategy for selecting enum members.                                                                                                          |
| `max_depth`             | `int`                       | `5`        | Maximum recursion depth before the cycle policy takes effect.                                                                                 |
| `cycle_policy`          | `reuse \ stub \ null`       | `reuse`    | How recursive references are resolved once depth or cycles are detected.                                                                      |
| `rng_mode`              | `portable \ legacy`         | `portable` | RNG implementation: portable SplitMix64 for cross-platform determinism or the legacy CPython RNG.                                             |
| `now`                   | `datetime \ null`           | `null`     | Anchor timestamp used for temporal values.                                                                                                    |
| `overrides`             | `dict[str, dict[str, Any]]` | `{}`       | Per-model overrides keyed by fully-qualified model name.                                                                                      |
| `provider_defaults`     | object                      | `{}`       | Reusable provider bundles and matching rules applied per type/annotation before heuristics.                                                   |
| `field_hints`           | object                      | `{mode = "none"}` | Prefer `Field` defaults/examples globally or per-model before falling back to providers.                                              |
| `field_policies`        | `dict[str, FieldPolicy]`    | `{}`       | Pattern-based overrides for specific fields.                                                                                                  |
| `locales`               | `dict[str, str]`            | `{}`       | Pattern-based Faker locale overrides for models or fields.                                                                                    |
| `emitters`              | object                      | see below  | Configure emitters such as pytest fixtures.                                                                                                   |
| `json`                  | object                      | see below  | Configure JSON emitters (shared by JSON/JSONL).                                                                                               |
| `paths`                 | object                      | see below  | Configure filesystem path providers (OS-specific generation).                                                                                 |
| `numbers`               | object                      | see below  | Control numeric distributions for ints/floats/decimals.                                                                                       |
| `heuristics`            | object                      | see below  | Enable or disable heuristic provider mapping.                                                                                                 |
| `respect_validators`    | `bool`                      | `false`    | Retry instance generation when model/dataclass validators raise errors.                                                                       |
| `validator_max_retries` | `int`                       | `2`        | Additional attempts made per instance when `respect_validators` is enabled.                                                                   |

### Validator retries

`respect_validators` tells the instance generator to treat `@field_validator`, `@model_validator`, and dataclass `__post_init__` failures as recoverable. Each rejection triggers a deterministic reseed (`validator_max_retries` controls how many extra attempts run), so invariants such as `start < end` or checksum math can be satisfied without hand-written fixtures. If retries are exhausted, CLI commands attach a `validator_failure` payload showing the offending validator, attempt counters, and the last set of field values. Toggle the behaviour globally via config/environment (`PFG_RESPECT_VALIDATORS` / `PFG_VALIDATOR_MAX_RETRIES`) or per run with `--respect-validators` and `--validator-max-retries`.

### JSON settings

| Key      | Type   | Default | Description                                    |
| -------- | ------ | ------- | ---------------------------------------------- |
| `indent` | `int`  | `2`     | Indentation level. Set `0` for compact output. |
| `orjson` | `bool` | `false` | Use `orjson` if installed for faster encoding. |

These values apply to both `pfg gen json` and JSONL emission. CLI flags `--indent` and `--orjson/--no-orjson` override them.

### Pytest emitter settings

| Key     | Type                          | Default     | Description              |
| ------- | ----------------------------- | ----------- | ------------------------ |
| `style` | `functions \ factory \ class` | `functions` | Fixture style structure. |
| `scope` | `function \ module \ session` | `function`  | Default fixture scope.   |

Change these values to adjust generated module ergonomics. CLI flags `--style` and `--scope` override them.

### Array settings

| Key            | Type        | Default       | Description                                                                       |
| -------------- | ----------- | ------------- | --------------------------------------------------------------------------------- |
| `max_ndim`     | `int`       | `2`           | Maximum number of dimensions for generated NumPy arrays.                          |
| `max_side`     | `int`       | `4`           | Maximum size for any axis; strategies respect both `max_side` and `max_elements`. |
| `max_elements` | `int`       | `16`          | Hard cap on the total number of elements in generated arrays.                     |
| `dtypes`       | `list[str]` | `["float64"]` | Allowed NumPy dtypes. Values must be accepted by `numpy.dtype`.                   |

Install the optional `pydantic-fixturegen[numpy]` extra to enable array providers. When arrays are disabled the configuration is ignored.

### Collection settings

Control how many elements list/set/tuple/mapping providers emit before field-level constraints are applied. Defaults keep collections small (`1-3` items) so diffs stay readable, but presets/CLI flags can expand them for stress testing.

| Key                | Type          | Default    | Description                                                                                      |
| ------------------ | ------------- | ---------- | ------------------------------------------------------------------------------------------------ |
| `min_items`        | `int`         | `1`        | Minimum number of elements to attempt before field constraints clamp the value.                  |
| `max_items`        | `int`         | `3`        | Soft maximum (still clamped by field constraints). Set equal to `min_items` for fixed sizes.     |
| `distribution`     | `"uniform" \ "min-heavy" \ "max-heavy"` | `"uniform"` | Bias random sampling toward the middle, the lower bound, or the upper bound of the configured span. |

CLI/API overrides: `--collection-min-items`, `--collection-max-items`, and `--collection-distribution` apply the same settings for a single run of `pfg gen json/dataset/fixtures` or `pfg persist`. Field policies accept `collection_min_items`, `collection_max_items`, and `collection_distribution` keys when you need per-field overrides (for example, forcing `Order.items` to emit at least five entries while leaving every other list alone).

Generation still honours schema constraints (`min_length`/`max_length`, tuple arity, typed `set[str]` etc.) by clamping whatever configuration you provide, so rules stay valid even when the overrides are aggressive.

### Identifier settings

| Key                   | Type        | Default     | Description                                                                     |
| --------------------- | ----------- | ----------- | ------------------------------------------------------------------------------- |
| `secret_str_length`   | `int`       | `16`        | Default length for generated `SecretStr` values (clamped by field constraints). |
| `secret_bytes_length` | `int`       | `16`        | Default length for generated `SecretBytes` values.                              |
| `url_schemes`         | `list[str]` | `["https"]` | Allowed URL schemes used by the identifier provider.                            |
| `url_include_path`    | `bool`      | `true`      | Include a deterministic path segment when generating URLs.                      |
| `uuid_version`        | `1 \ 4`     | `4`         | UUID version emitted by the `uuid` provider.                                    |
| `mask_sensitive`      | `bool`      | `false`     | Mask identifiers with reserved example domains, IPs, and card numbers.          |

Identifier settings apply to `EmailStr`, `HttpUrl`/`AnyUrl`, secret strings/bytes, payment cards, and IP address fields. Values are chosen via the seeded RNG so fixtures remain reproducible across runs.

> **Note:** Email validation relies on the optional `email` extra. Install it with `pip install "pydantic-fixturegen[email]"` when you need `EmailStr` support.

> **Note:** Payment card fields use the optional `payment` extra backed by `pydantic-extra-types`. Install it with `pip install "pydantic-fixturegen[payment]"` to enable typed `PaymentCardNumber` support.

### Cycle handling

| Key            | Type                  | Default | Description                                                 |
| -------------- | --------------------- | ------- | ----------------------------------------------------------- |
| `max_depth`    | `int`                 | `5`     | Maximum recursion depth before the cycle policy is applied. |
| `cycle_policy` | `reuse \ stub \ null` | `reuse` | Controls how recursive or cyclic references are resolved.   |

- `reuse` clones an existing instance of the same model (deterministically) so downstream consumers still receive populated data. If no exemplar exists yet, fixturegen falls back to a stub.
- `stub` emits a minimal instance produced via `model_construct()` / dataclass defaults so schemas remain intact without pretending real data exists.
- `null` returns `None`, which matches the previous behaviour but now must be explicitly requested.
- JSON and fixture outputs now include a reserved `__cycles__` array per model entry whenever a recursive policy fires. Each entry lists the field path, policy, and reference path (when known), so reviewers can tell which parts reused data without diffing entire payloads.
- Cycle metadata is emitted for both true recursion detection and depth-limit fallbacks, so even `max_depth` safeguards surface the exact policy (`reuse`, `stub`, or `null`) applied at each field.
- CLI overrides: `--max-depth` adjusts the recursion budget per run, and `--on-cycle` selects the policy (`reuse`, `stub`, or `null`).

### RNG mode

Set `rng_mode = "legacy"` to temporarily keep CPython's Mersenne Twister RNG (matching pydantic-fixturegen 1.1 and earlier). The default `portable` mode uses a SplitMix64-based generator implemented in Python, so identical seeds produce byte-for-byte identical datasets on every supported OS and Python release. Override via `PFG_RNG_MODE`, `--rng-mode`, or configuration when migrating large snapshot suites.

### Heuristic settings

| Key       | Type   | Default | Description                                                                                                                              |
| --------- | ------ | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `enabled` | `bool` | `true`  | Turn the semantic rule engine on or off. Set to `false` (or `PFG_HEURISTICS__ENABLED=false`) to fall back to plain type-based providers. |

When enabled, the engine inspects field names, aliases, constraints, and `Annotated` metadata to choose richer providers automatically (emails, slugs, ISO country/language codes, filesystem paths, etc.). The provenance for each decision shows up in `pfg gen explain` so you can see which rule fired and why. Disable heuristics if you prefer to manage overrides solely through `[field_policies]` or plugins.

### Number distribution settings

| Key                      | Type                             | Default     | Description                                                                                    |
| ------------------------ | -------------------------------- | ----------- | ---------------------------------------------------------------------------------------------- |
| `distribution`           | `"uniform" \ "normal" \ "spike"` | `"uniform"` | Base distribution applied to ints/floats/decimals.                                             |
| `normal_stddev_fraction` | `float`                          | `0.25`      | When `distribution="normal"`, standard deviation expressed as a fraction of the min/max range. |
| `spike_ratio`            | `float`                          | `0.7`       | For `distribution="spike"`, probability of sampling inside the spike window.                   |
| `spike_width_fraction`   | `float`                          | `0.1`       | Width of the spike window (fraction of the min/max range).                                     |

`normal` sampling is truncated to the configured bounds so values remain deterministic. `spike` mode biases generation toward the midpoint (`spike_ratio` chance) while occasionally falling back to uniform sampling to explore outliers.

### Path settings

| Key          | Type                                     | Default   | Description                                                      |
| ------------ | ---------------------------------------- | --------- | ---------------------------------------------------------------- |
| `default_os` | `"posix" \ "windows" \ "mac"`            | `"posix"` | Baseline OS flavour applied to generated filesystem paths.       |
| `models`     | `dict[str, "posix" \ "windows" \ "mac"]` | `{}`      | Override the target OS for matching model names (glob patterns). |

Path settings cover `pathlib.Path`, `pydantic.DirectoryPath`, and `pydantic.FilePath` fields so fixtures can mimic Windows drive letters, macOS bundles, or POSIX roots regardless of the host platform.

Example TOML:

```toml
[tool.pydantic_fixturegen.paths]
default_os = "windows"
models = {"app.models.Reporting.*" = "mac", "legacy.schemas.*" = "posix"}
```

The same structure works via YAML or environment variables (`PFG_PATHS__MODELS__legacy.schemas.*=posix`), letting you target specific models without changing the global default.

### Polyfactory settings

| Key                 | Type        | Default | Description                                                                             |
| ------------------- | ----------- | ------- | --------------------------------------------------------------------------------------- |
| `enabled`           | `bool`      | `true`  | Toggle automatic detection of Polyfactory factories.                                    |
| `prefer_delegation` | `bool`      | `true`  | When `false`, detection logs what it found but generation stays on the built-in engine. |
| `modules`           | `list[str]` | `[]`    | Additional modules to import when scanning for `ModelFactory` subclasses.               |

When enabled, the CLI/API inspects every discovered module (plus `<package>.factories` heuristics and any extra modules you list) for subclasses of `polyfactory.factories.pydantic_factory.ModelFactory`. Matching factories become delegates for their `__model__` so nested models, JSON output, and pytest fixtures reuse existing Polyfactory logic transparently. Set `prefer_delegation = false` if you only need the metadata surfaced in logs or plan to call the new `pfg gen polyfactory` exporter manually.

Environment overrides follow the usual pattern:

```bash
export PFG_POLYFACTORY__ENABLED=false
export PFG_POLYFACTORY__MODULES=app.factories,tests.factories
```

The CLI still respects per-command `--include`/`--exclude` filters; only factories whose models are actually in scope will be attached.

### Per-field overrides

Use `[tool.pydantic_fixturegen.overrides]` when you need Polyfactory-style overrides without writing factories:

```toml
[tool.pydantic_fixturegen.overrides."app.models.User".token]
value = "demo-token"

[tool.pydantic_fixturegen.overrides."app.models.User".slug]
factory = "app.factories:build_slug"
factory_kwargs = { prefix = "user" }

[tool.pydantic_fixturegen.overrides."app.models.User".legacy_id]
require = true

[tool.pydantic_fixturegen.overrides."app.models.User".joined_name]
value = ""
post_generate = "app.factories:join_fields"

[tool.pydantic_fixturegen.overrides."app.models.User".email]
provider = "string"
provider_kwargs = { length = 12 }
```

| Key                                                | Description                                                                                                                           |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `value` / `use`                                    | Literal value to inject (deep-copied so shared state is safe).                                                                        |
| `factory`                                          | Callable expressed as `module.path:attr` (or dotted module path). Receives `(context, *args, **kwargs)`.                              |
| `factory_args` / `factory_kwargs`                  | Optional arguments forwarded to the factory callable.                                                                                 |
| `ignore`                                           | Skip populating the field so model defaults apply.                                                                                    |
| `require`                                          | Fail fast unless a `value`/`factory` is supplied (mirrors Polyfactory’s `Require`).                                                   |
| `post_generate`                                    | Callable executed after the field’s value is produced. Signature matches factories, but receives `(value, context, *args, **kwargs)`. |
| `provider` / `provider_format` / `provider_kwargs` | Override the provider/type registered in the registry.                                                                                |
| `p_none`, `enum_policy`, `union_policy`            | Per-field policy overrides on top of the global settings.                                                                             |

`context` is a `FieldOverrideContext` exposing the model class, field name, alias, Faker/random handles, path, and the partially-populated `values` mapping.

The CLI mirrors the file format via `--override/-O`:

```bash
pfg gen json models.py --override 'app.models.User.token={"value": "demo"}' \
                       --override 'app.models.User.slug={"factory": "app.factories:build_slug"}'
```

Overrides participate in the same precedence chain as the rest of the config (pyproject < env < CLI), so you can keep long-lived defaults in TOML and apply run-specific tweaks from the command line.

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

### Type-level provider defaults

Define reusable bundles when entire annotation families should share the same provider without repeating CLI overrides. Each bundle names a provider type (and optional format/kwargs); rules bind bundles to field summaries by matching `FieldSummary.type`, annotation paths, or `typing.Annotated` metadata.

```toml
[tool.pydantic_fixturegen.provider_defaults.bundles.masked_email]
provider = "email"
[tool.pydantic_fixturegen.provider_defaults.bundles.masked_email.provider_kwargs]
mask_sensitive = true

[tool.pydantic_fixturegen.provider_defaults.bundles.short_slug]
provider = "string"
provider_format = "slug"
[tool.pydantic_fixturegen.provider_defaults.bundles.short_slug.provider_kwargs]
max_length = 16

[[tool.pydantic_fixturegen.provider_defaults.rules]]
name = "typed-email"
bundle = "masked_email"
annotation_globs = ["pydantic.*EmailStr"]

[[tool.pydantic_fixturegen.provider_defaults.rules]]
name = "annotated-slug"
bundle = "short_slug"
summary_types = ["string"]
metadata = ["annotated_types.MinLen"]
```

- Rules accept `summary_types`, `formats`, `annotation_globs`, `metadata`/`metadata_all`, and `metadata_any`. Metadata entries reference the fully-qualified class name of the metadata object (e.g., `annotated_types.MinLen`), so any `typing.Annotated[..., MinLen(3)]` field can opt into a bundle without matching by field name.
- Configuration order determines precedence: the first matching rule wins, per-field overrides still take top priority, and heuristics only run when no type-level rule applies.
- Use `provider_kwargs` on bundles to pass static arguments (for example, enable masked identifier output everywhere or cap slug lengths) and keep CLI invocations free of repeated `--override` flags.

### Field hints

Prefer `Field(default=...)` or `Field(examples=...)` values before falling back to providers.

```toml
[tool.pydantic_fixturegen.field_hints]
mode = "defaults-then-examples"

[tool.pydantic_fixturegen.field_hints.models]
"*.Address" = "examples"
"legacy.*" = "examples-then-defaults"
```

- Global mode accepts `none`, `defaults`, `examples`, `defaults-then-examples`, or `examples-then-defaults`. Modes describe the priority order when both defaults and examples exist.
- Per-model overrides (glob patterns) force specific models into a different mode without touching the rest of the run.
- The `--field-hints` flag is available on `pfg gen json`, `pfg gen dataset`, and `pfg gen fixtures` for one-off overrides.
- Hints sit above heuristics but below explicit per-field overrides, so manual provider swaps still win when configured.
- Field defaults are deep-cloned (`default_factory` is invoked) and BaseModel defaults use `model_copy(deep=True)` so nested data stays isolated between samples.

### Persistence handlers

Register reusable persistence handlers under `[tool.pydantic_fixturegen.persistence.handlers]` and reference them via `pfg persist --handler <name>`.

```toml
[tool.pydantic_fixturegen.persistence.handlers.sqlite]
path = "pydantic_fixturegen.persistence.handlers:SQLiteJSONPersistenceHandler"
[tool.pydantic_fixturegen.persistence.handlers.sqlite.options]
database = "./artifacts/persist.db"
table = "fixtures"

[tool.pydantic_fixturegen.persistence.handlers.capture]
path = "tests.persistence_helpers:SyncCaptureHandler"
kind = "sync"
```

- `path` points to a callable or class (`module:attr`) that returns a handler instance. Built-in shortcuts (`http-post`, `http-post-async`, `sqlite-json`) are registered automatically.
- `kind` is optional—fixturegen inspects handler methods to determine whether they are sync or async. Set it explicitly when the callable dynamically switches behaviour.
- Nested `[options]` sections supply keyword arguments for handler construction (`url`, `headers`, etc.). CLI `--handler-config '{...}'` merges on top of the configured defaults.
- Entry-point plugins can register handlers in code via `pfg_register_persistence_handlers(registry)`, allowing reusable handler suites without editing configuration.

### Locale overrides

Add a `locales` mapping when you need region-specific Faker providers:

```toml
[tool.pydantic_fixturegen.locales]
"app.models.User.*" = "sv_SE"
"app.models.User.email" = "en_GB"
```

- Patterns follow the same rules as `field_policies` (glob or `re:`-prefixed regex).
- Field-level entries override broader model matches; unmatched paths fall back to the global `locale`.
- You can omit the trailing `.*` for model-wide overrides — `"app.models.User"` and `"app.models.User.*"` behave the same, as does using bare class names such as `"User"`.
- Configuration loading validates locales by instantiating `Faker(locale)`, so typos raise descriptive errors.

### Profiles

Profiles bundle deterministic overrides. Privacy-focused profiles harden identifiers, while adversarial profiles bias generation toward tricky boundary cases. Set `profile = "pii-safe"` under `[tool.pydantic_fixturegen]`, export `PFG_PROFILE`, or pass `--profile` to any generation/diff command. Profiles are applied before the rest of your configuration just like presets, so you can layer extra overrides on top.

- `pii-safe` — masks identifier providers (example.com emails, example.invalid URLs, reserved IPs, test card numbers) and raises `p_none` for `*.email`, `*.phone*`, `*.ssn`, `*.tax_id`, etc.
- `realistic` — disables masking, restores URL path emission, and keeps contact fields populated for staging/stress environments.
- `edge` — toggles random enum/union selection, shifts numeric distributions to narrow spikes near min/max, and increases `p_none` on fields mentioning counts or limits.
- `adversarial` — maximizes optional `None` return rates, constrains collection sizes to 0–2 elements, and narrows numeric spikes even further to exercise validators.

## Environment variable cheatsheet

| Purpose              | Variable                                      | Example                                                  |
| -------------------- | --------------------------------------------- | -------------------------------------------------------- |
| Profile              | `PFG_PROFILE`                                 | `export PFG_PROFILE=adversarial`                         |
| Numeric distribution | `PFG_NUMBERS__DISTRIBUTION`                   | `export PFG_NUMBERS__DISTRIBUTION=normal`                |
| RNG mode             | `PFG_RNG_MODE`                                | `export PFG_RNG_MODE=legacy`                             |
| Seed override        | `PFG_SEED`                                    | `export PFG_SEED=1234`                                   |
| JSON indent          | `PFG_JSON__INDENT`                            | `export PFG_JSON__INDENT=0`                              |
| Enable orjson        | `PFG_JSON__ORJSON`                            | `export PFG_JSON__ORJSON=true`                           |
| Fixture style        | `PFG_EMITTERS__PYTEST__STYLE`                 | `export PFG_EMITTERS__PYTEST__STYLE=factory`             |
| Fixture scope        | `PFG_EMITTERS__PYTEST__SCOPE`                 | `export PFG_EMITTERS__PYTEST__SCOPE=session`             |
| Field policy update  | `PFG_FIELD_POLICIES__*.User.nickname__P_NONE` | `export PFG_FIELD_POLICIES__*.User.nickname__P_NONE=0.2` |
| Array max ndim       | `PFG_ARRAYS__MAX_NDIM`                        | `export PFG_ARRAYS__MAX_NDIM=3`                          |
| Secret string length | `PFG_IDENTIFIERS__SECRET_STR_LENGTH`          | `export PFG_IDENTIFIERS__SECRET_STR_LENGTH=24`           |
| Secret bytes length  | `PFG_IDENTIFIERS__SECRET_BYTES_LENGTH`        | `export PFG_IDENTIFIERS__SECRET_BYTES_LENGTH=32`         |
| URL schemes          | `PFG_IDENTIFIERS__URL_SCHEMES`                | `export PFG_IDENTIFIERS__URL_SCHEMES=https,ftp`          |
| URL include path     | `PFG_IDENTIFIERS__URL_INCLUDE_PATH`           | `export PFG_IDENTIFIERS__URL_INCLUDE_PATH=false`         |
| UUID version         | `PFG_IDENTIFIERS__UUID_VERSION`               | `export PFG_IDENTIFIERS__UUID_VERSION=1`                 |
| Path target          | `PFG_PATHS__DEFAULT_OS`                       | `export PFG_PATHS__DEFAULT_OS=windows`                   |
| Model path target    | `PFG_PATHS__MODELS__app.models.User`          | `export PFG_PATHS__MODELS__app.models.User=mac`          |

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
