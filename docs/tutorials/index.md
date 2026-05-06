# Tutorials

Skaal is easiest to learn as a sequence, not as a reference dump. The tutorials below are deliberately progressive: each one adds a single new layer to the same mental model.

1. declare storage and compute
2. run locally
3. mount a public HTTP framework when you need one
4. solve a target-specific plan
5. generate and deploy artifacts from that plan

Every tutorial is grounded in an existing example or public API surface from this repository.

## Recommended Path

| Tutorial | Focus | Draws from |
| --- | --- | --- |
| [1. Build a Counter App](first-app.md) | `App`, `Store`, `@app.storage`, `@app.function`, local run loop | `examples/counter.py`, `examples/01_hello_world/app.py` |
| [2. Add a FastAPI Surface](http-api.md) | Mounted ASGI, `app.invoke(...)`, public routes | `examples/02_todo_api/app.py`, `examples/06_fastapi_streaming/app.py` |
| [3. Plan, Build, and Deploy](planning-and-deployment.md) | Catalogs, `plan.skaal.lock`, build artifacts, deploy loop | `skaal/cli/*.py`, `catalogs/*.toml` |
| [4. Relational Data and Migrations](relational-and-migrations.md) | SQLModel storage, `open_relational_session`, relational CLI | `examples/02_todo_api/app.py`, `skaal/cli/migrate/relational_cmd.py` |
| [5. Files and Streaming](files-and-streaming.md) | `BlobStore`, pagination, `app.invoke_stream(...)` | `examples/07_file_upload_api/app.py`, `examples/06_fastapi_streaming/app.py` |

## Before You Begin

Install the local run loop and runtime helpers:

```bash
pip install "skaal[serve,runtime]"
```

For the HTTP and upload tutorials, add FastAPI support:

```bash
pip install "skaal[fastapi]"
```

If you want a project with the Skaal config already in place, scaffold one first:

```bash
skaal init demo
cd demo
pip install -e .
```

That gives you a `pyproject.toml` with `[tool.skaal] app = "demo.app:app"`, which keeps later commands short.

## What This Track Covers

- stable local development with `skaal run`
- the mounted HTTP model for FastAPI or another ASGI framework
- the solver workflow behind `skaal plan`
- local and cloud-shaped artifact generation through `skaal build`
- relational migrations through `skaal migrate relational`
- blob uploads and streaming responses

## What It Does Not Cover

This track intentionally leaves out the mesh runtime and other experimental surfaces. The goal here is to teach the stable workflow that shows up across the examples, CLI commands, and tests in the repository.

## Start Here

Begin with [Tutorial 1: Build a Counter App](first-app.md).
