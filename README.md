<div id="top"></div>

# Skaal

[![CI](https://img.shields.io/github/actions/workflow/status/Elouen-ginat/Skaal/ci.yml?branch=main&label=CI)](https://github.com/Elouen-ginat/Skaal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-2E8B57)](LICENSE)
[![Targets](https://img.shields.io/badge/targets-local%20%7C%20AWS%20%7C%20GCP-0F766E)](#platform-features)
[![Deploy](https://img.shields.io/badge/deploy-Pulumi%20generated-8A2BE2)](#how-it-works)

**Infrastructure as Constraints** for Python.

Build your app once, declare the behavior you need, and let Skaal choose the cheapest backend that satisfies it for local development, AWS, or GCP.

`Python 3.11+` `Z3 solver` `Local-first` `AWS` `GCP` `ASGI` `FastAPI` `Dash` `Blob storage` `Vector search` `Pulumi`

## Contents

- [Why Skaal](#why-skaal)
- [What You Get](#what-you-get)
- [Quickstart](#quickstart)
- [How It Works](#how-it-works)
- [Platform Features](#platform-features)
- [Installation](#installation)
- [Examples](#examples)
- [Documentation](#documentation)
- [Project Status](#project-status)
- [License](#license)

## Why Skaal

Most frameworks force infrastructure decisions too early. Skaal reverses that model.

Instead of hard-coding SQLite, Redis, Postgres, S3, Firestore, or DynamoDB into business logic, you declare constraints such as latency, durability, throughput, access pattern, and scale. Skaal then plans an implementation that fits the target environment and catalog you provide.

That gives you a cleaner development story and a stronger deployment story:

- Start local without rewriting the application later.
- Keep infrastructure choices out of business code.
- Generate deployment artifacts instead of hand-maintaining them.
- Move between local, AWS, and GCP using the same application model.
- Let the solver pick the least expensive backend that still meets requirements.

[Back to top](#top)

## What You Get

| Capability | What Skaal provides |
|---|---|
| Constraint-based planning | A Z3-backed solver that selects viable backends from TOML catalogs |
| Storage abstractions | Typed key-value, collection, blob, relational, and vector surfaces |
| Compute model | Decorators for compute, scale, handlers, schedules, and shared resources |
| Local runtime | ASGI serving, hot-reload workflow, local channels, and local backend support |
| Deployment pipeline | Generated Dockerfiles, entrypoints, Pulumi programs, and stack metadata |
| Cloud targets | AWS and GCP deployment flows driven from the same app definition |
| Extensibility | Plugin-based backend and channel registration via entry points |

[Back to top](#top)

## Quickstart

Install Skaal for local development:

```bash
pip install "skaal[serve]"
skaal init demo
cd demo
pip install -e .
skaal run
```

If your app uses schedules, JWT auth, background jobs, or telemetry hooks, install runtime support too:

```bash
pip install "skaal[serve,runtime]"
```

Minimal example:

```python
from skaal import App, Map

app = App("hello")


@app.storage(read_latency="< 10ms", durability="ephemeral")
class Counters(Map[str, int]):
    pass
```

For HTTP APIs, Skaal's recommended pattern is to mount an ASGI framework and invoke Skaal compute from handlers. FastAPI, Starlette, and Dash fit well in that model.

[Back to top](#top)

## How It Works

1. **Declare constraints** with decorators such as `@storage`, `@compute`, `@blob`, and `@scale`.
2. **Plan infrastructure** from a catalog using the Z3 solver.
3. **Build artifacts** for the chosen target.
4. **Run locally or deploy** to local, AWS, or GCP.

Typical flow:

```bash
skaal plan --app myapp:app --catalog catalogs/local.toml
skaal build --app myapp:app --target local --catalog catalogs/local.toml
skaal deploy --app myapp:app --target local --catalog catalogs/local.toml
```

Local deployment is Pulumi-based and produces artifacts such as a `Dockerfile`, `main.py`, `Pulumi.yaml`, and stack metadata under `artifacts/`.

[Back to top](#top)

## Platform Features

### Storage and Data

- `Map[K, V]` and `Collection[T]` for typed application storage.
- `BlobStore` for file and object workflows.
- Relational and vector tiers for workloads that need SQL or embeddings.
- Backend catalogs for local, AWS, and GCP environments.

### Runtime and App Model

- Composable `Module` and `App` abstractions.
- Async-first runtime design.
- Local and Redis channel wiring.
- Scheduling primitives and runtime hooks.
- Optional mesh runtime via the `skaal-mesh` package.

### Deployment

- Local target for Docker-backed development deployment.
- AWS and GCP packaging and deployment flows.
- Generated Pulumi programs instead of handwritten infrastructure glue.
- Target-specific dependency resolution through build settings in `pyproject.toml`.

### Framework Integration

- FastAPI support, including multipart uploads.
- Dash support for UI applications.
- Example apps covering CRUD APIs, streaming, uploads, dashboards, and counters.

[Back to top](#top)

## Installation

Base install:

```bash
pip install skaal
```

Optional extras:

| Extra | Purpose |
|---|---|
| `skaal[serve]` | Local serving, hot reload, and ASGI/WSGI runtime support |
| `skaal[runtime]` | Schedules, JWT auth, OpenTelemetry hooks, and runtime services |
| `skaal[deploy]` | Docker and Pulumi deployment tooling |
| `skaal[aws]` | AWS provider and storage dependencies |
| `skaal[gcp]` | GCP provider and storage dependencies |
| `skaal[vector]` | Vector and embedding backend dependencies |
| `skaal[fastapi]` | FastAPI and multipart upload support |
| `skaal[dash]` | Dash and dash-bootstrap-components |
| `skaal[examples]` | Dependencies needed for bundled example apps |
| `skaal[mesh]` | Prebuilt distributed mesh runtime wheel |
| `skaal[secrets-aws]` | AWS secret manager integration |
| `skaal[secrets-gcp]` | GCP secret manager integration |

Common setups:

```bash
# Local development
pip install "skaal[serve,runtime]"

# AWS deployment
pip install "skaal[deploy,aws,runtime]"

# GCP deployment
pip install "skaal[deploy,gcp,runtime]"
```

[Back to top](#top)

## Examples

The repository includes runnable examples for common application shapes:

- Hello world
- Todo API
- FastAPI streaming
- File upload API
- Dash app
- Mesh counter
- Task dashboard
- Team directory

Start by browsing [examples](examples) and the generated local deployment output in [artifacts](artifacts).

[Back to top](#top)

## Documentation

- [CLI guide](docs/cli.md)
- [HTTP integration](docs/http.md)
- [Catalogs](docs/catalogs.md)
- [Backend unification notes](docs/backend_unification.md)
- [Runtime audit](docs/runtime_audit.md)
- [Architecture decisions](docs/design)

[Back to top](#top)

## Project Status

Skaal is currently **alpha**. The core direction is stable: constraint declaration, backend planning, generated deployment artifacts, and local or cloud execution from one codebase. Expect API refinement as the storage, runtime, deploy, and mesh surfaces continue to mature.

## License

GPL-3.0-or-later
