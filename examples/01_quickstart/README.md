# 01 — Quickstart

The smallest end-to-end Skaal app. A Dash UI lets you increment and reset
named counters that live in a constraint-declared `Store[int]`.

## What it shows

- `App` — the central registry that the runtime, planner, and deploy
  generators all read from.
- `@app.storage(...)` + `Store[int]` — declare typed storage with
  constraints (`read_latency`, `durability`). The Z3 solver picks the
  cheapest backend that satisfies them.
- `@app.function()` — async business logic the runtime wraps with retry,
  rate-limit, and circuit-breaker policies.
- `app.mount_wsgi(...)` — co-host a Dash UI inside the Skaal runtime so a
  single `python app.py` serves both.

## Run

```bash
pip install "skaal[serve,examples]" dash dash-bootstrap-components
python examples/01_quickstart/app.py
```

Then open [http://localhost:8050](http://localhost:8050).

## Try it on a different target

The exact same source plans and deploys to AWS without code changes:

```bash
skaal plan examples.01_quickstart.app:app --target aws --catalog catalogs/aws.toml
```

The solver swaps `LocalMap` for DynamoDB; the function bodies are untouched.
