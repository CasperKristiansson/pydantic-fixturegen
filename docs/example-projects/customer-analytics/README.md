# Customer analytics example

This miniature project mirrors a metrics/segmentation workflow. It exposes loyalty profiles, purchase/session events, and a `SegmentSnapshot` model that powers datasets and Hypothesis strategies.

## What it demonstrates

- **Dataset + strategy parity.** `make datasets` writes `samples/segments.jsonl` for downstream analytics pipelines, while `make strategies` exports Hypothesis strategies so the same generator powers property-based tests.
- **Deterministic knobs.** `pyproject.toml` commits a global seed, freeze file, JSON logging, and field hints so regenerated samples remain stable. All commands also pass `--now 2025-01-01T00:00:00Z`.
- **Package discovery.** The CLI targets `models/segments.py`, but you can point `pfg list`/`pfg gen` at the entire `models/` folder now that directory targets are supported.

## Run it locally

```bash
cd docs/example-projects/customer-analytics
make install     # set up .venv pinned to the repo
make datasets    # regenerate samples/segments.jsonl
make strategies  # refresh samples/segments_strategies.py
```

## Files of interest

- `models/shared.py` — common telemetry primitives (base events, money, locales).
- `models/events.py` — purchase + session events referencing shared models.
- `models/segments.py` — `SegmentFilter` and `SegmentSnapshot`, the primary CLI target.
- `samples/segments.jsonl` — committed JSONL dataset that guards analytics pipelines.
- `samples/segments_strategies.py` — Hypothesis strategies exported by fixturegen.
