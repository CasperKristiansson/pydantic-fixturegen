# Example projects

Use the embedded projects below to explore fixturegen workflows without wiring your own repo first. Each folder is runnable end-to-end and mirrors a common adoption story.

## FastAPI marketplace

- **Path:** [`docs/example-projects/fastapi-marketplace`](fastapi-marketplace/README.md)
- **Stack:** FastAPI + Polyfactory delegation + snapshot-heavy CI
- **Highlights:** Multi-module order/customer/payment models, Makefile targets for JSON + pytest fixtures, committed `.pfg-seeds.json`, GitHub Actions workflow for `pfg snapshot verify`, optional delegation into existing `ModelFactory` classes.
- **Try it:** `cd docs/example-projects/fastapi-marketplace && make install && make snapshots`

## Customer analytics

- **Path:** [`docs/example-projects/customer-analytics`](customer-analytics/README.md)
- **Stack:** Analytics datasets + Hypothesis strategies
- **Highlights:** Dataset export via `pfg gen json --jsonl`, Hypothesis strategy export (`pfg gen strategies`), deterministic seeds/NOW anchor, example JSONL payloads for telemetry checks.
- **Try it:** `cd docs/example-projects/customer-analytics && make install && make datasets && make strategies`
