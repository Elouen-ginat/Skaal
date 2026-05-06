# Getting Started

Skaal makes the most sense as one loop: declare the behavior your app needs, run it locally, solve a target-specific plan, then build and deploy from that same app model. This page gets you to that loop quickly and points you at the guided tutorials.

## Install

Start with the local run loop and runtime extras:

```bash
pip install "skaal[serve,runtime]"
```

Add extras only when you need them:

```bash
pip install "skaal[fastapi]"   # mounted FastAPI routes and multipart uploads
pip install "skaal[vector]"    # vector search examples and tutorials
```

## Choose Your Starting Point

### Scaffold a project

If you want Skaal to configure `pyproject.toml` for you, start here:

```bash
skaal init demo
cd demo
pip install -e .
skaal run
```

The scaffold writes `[tool.skaal] app = "demo.app:app"`, which means later commands like `skaal migrate relational upgrade` can resolve your app without repeating `MODULE:APP` on every call.

### Run the bundled counter example

If you want the shortest path to a running app, use the repository example directly:

```bash
pip install "skaal[examples]"
skaal run examples.counter:app
```

Then open a second terminal and try:

```bash
curl -s http://127.0.0.1:8000/increment \
    -H "Content-Type: application/json" \
    -d '{"name": "hits"}'

curl -s http://127.0.0.1:8000/list_counts \
    -H "Content-Type: application/json" \
    -d '{}'
```

## The Progressive Tutorial Track

The tutorials are intentionally simple and build one idea at a time.

| Tutorial | Outcome |
| --- | --- |
| [1. Build a Counter App](tutorials/first-app.md) | Learn `App`, `Store`, `@app.storage`, `@app.function`, and the local HTTP surface. |
| [2. Add a FastAPI Surface](tutorials/http-api.md) | Mount FastAPI and route public HTTP through `app.invoke(...)`. |
| [3. Plan, Build, and Deploy](tutorials/planning-and-deployment.md) | Use catalogs, inspect `plan.skaal.lock`, then generate and deploy artifacts. |
| [4. Relational Data and Migrations](tutorials/relational-and-migrations.md) | Add SQLModel-backed storage and use the Alembic-powered migration commands. |
| [5. Files and Streaming](tutorials/files-and-streaming.md) | Handle blob uploads and stream responses from Skaal functions. |

If you want the overview first, read [Tutorial Overview](tutorials/index.md).

## The Core Command Loop

The CLI revolves around the plan file.

```bash
skaal plan examples.counter:app --target local --catalog catalogs/local.toml
skaal diff
skaal build --out artifacts
skaal deploy --artifacts-dir artifacts
```

That writes `plan.skaal.lock`, generates a self-contained `artifacts/` directory, and applies the local Pulumi stack. To retarget the same app, change the target and catalog instead of rewriting your business logic.

## Where To Go Next

- Read [Tutorial Overview](tutorials/index.md) if you want the guided path.
- Read [CLI](cli.md) for the full command surface.
- Read [HTTP Integration](http.md) for the mounted ASGI model.
- Read [Examples](examples.md) to jump into the full repository apps.
- Read [Python API](reference/python-api.md) if you want to drive the planner in-process.
