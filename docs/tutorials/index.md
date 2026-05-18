# Tutorials

Skaal is easiest to learn as a sequence, not as a reference dump. Each tutorial adds one new layer to the same model: declare the app, run it locally, mount public HTTP when you need it, then bind and deploy it by environment.

## Recommended Path

| Tutorial | Focus | Draws from |
| --- | --- | --- |
| [1. Your first app](first-app.md) | `App`, `Store`, `@app.storage`, `@app.expose`, local run loop | `examples/counter.py` |
| [2. Adding HTTP routes](http-api.md) | Mounted ASGI, `app.invoke(...)`, public routes | `examples/todo_api/app.py`, `examples/fastapi_streaming/app.py` |
| [3. Deploying a simple AWS app](planning-and-deployment.md) | AWS preflight, `skaal.toml`, `skaal.lock`, preview, deploy, live verification | `examples/counter_api.py`, `skaal/cli/*.py` |
| [3b. Deploying a simple GCP app](gcp-deployment.md) | GCP ADC preflight, project config, preview, deploy, and Cloud Run verification | `examples/counter_api.py`, `skaal/deploy/gcp/*.py` |
| [4. Relational data](relational-and-migrations.md) | SQLModel storage, `Table.session()`, relational model shape | `examples/todo_api/app.py` |
| [5. Files and Streaming](files-and-streaming.md) | `BlobStore`, pagination, `app.invoke_stream(...)` | `examples/file_upload_api/app.py`, `examples/fastapi_streaming/app.py` |

## Before You Begin

Install the local runtime:

```bash
pip install "skaal[serve]"
```

For the HTTP and upload tutorials, add FastAPI support:

```bash
pip install "skaal[fastapi]"
```

For the deploy tutorials, add the deploy extras for your target:

```bash
pip install "skaal[deploy,aws]"
pip install "skaal[deploy,gcp]"
```

What you will be able to do after this track:

- build and run a Skaal app from one file
- mount FastAPI on top of Skaal compute
- define named environments in `skaal.toml`
- render and deploy artifacts for one environment
- use `Table`, `BlobStore`, and streaming responses in realistic app shapes

## What this does not cover

- project scaffolding through `skaal init`
- the public migration command group
- experimental runtime surfaces

## Start Here

Begin with [Tutorial 1: Your first app](first-app.md).
