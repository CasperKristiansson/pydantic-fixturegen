# Presets: apply opinionated policy bundles

> Switch between ready-made strategies without editing configuration files.

## Available presets

| Name           | Behaviour                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------- |
| `boundary`     | Randomises unions/enums, sets `p_none` ≈ 0.35, keeps JSON pretty-printed.                   |
| `boundary-max` | Aggressive edge exploration with `p_none` ≈ 0.6, compact JSON (`indent=0`), and shard bias. |

- Aliases like `edge` resolve to `boundary`.
- Presets load before other configuration layers; CLI/env values still override them.

## Usage

```bash
pfg gen json ./models.py --out ./out/users.json --preset boundary

pfg gen fixtures ./models.py --out tests/fixtures/test_users.py --preset boundary-max
```

- Combine with `--seed` or frozen seeds for deterministic behaviour.
- Verify the effect via `pfg gen explain` or by inspecting metadata banners.

## Interaction with configuration

- Presets mutate the in-memory configuration only for the current command.
- Any explicit values you pass through CLI or environment take precedence.
- When you need project-wide defaults, set them directly in `[tool.pydantic_fixturegen]`.

Use presets with [field policies](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/configuration.md#field-policy-schemas) for precise overrides on top of the bundled opinion.
