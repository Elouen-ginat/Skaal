<div id="top"></div>

# Skaal

[![CI](https://img.shields.io/github/actions/workflow/status/Elouen-ginat/Skaal/ci.yml?branch=main&label=CI)](https://github.com/Elouen-ginat/Skaal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-2E8B57)](LICENSE)
[![Targets](https://img.shields.io/badge/targets-local%20%7C%20AWS%20%7C%20GCP-0F766E)](#platform-features)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#project-status)

**Infrastructure as Constraints for Python.**

You picked SQLite to start. Six months later you rewrote the data layer for Postgres, then again for DynamoDB when traffic moved. Each migration leaked infra concerns into business code, and your Pulumi or Terraform now duplicates what your app already declares.

Skaal flips the model: declare the *behavior* you need (latency, durability, throughput, residency, access pattern), and a Z3 solver picks the cheapest backend in your catalog that satisfies it — local, AWS, or GCP — from one application file.

Documentation: [https://elouen-ginat.github.io/Skaal/](https://elouen-ginat.github.io/Skaal/)

## Contents

- [Before / After](#before--after)
- [How It Differs](#how-it-differs)
- [Quickstart](#quickstart)
- [How It Works](#how-it-works)
- [Platform Features](#platform-features)
- [Installation](#installation)
- [Examples](#examples)
- [When Skaal Isn't a Fit](#when-skaal-isnt-a-fit)
- [Project Status](#project-status)
- [Documentation & FAQ](#documentation--faq)
- [License](#license)

## Before / After

Without Skaal, a single resource pulls in a backend client, an Alembic or schema setup, and Pulumi wiring — and the choice is baked into your code:

```python
# app.py — backend choice hard-coded
import boto3
ddb = boto3.resource("dynamodb")
table = ddb.Table("todos")          # provisioned in pulumi/__main__.py
def get(k): return table.get_item(Key={"id": k})["Item"]
```

With Skaal, you declare the contract. The solver picks DynamoDB on AWS, SQLite locally, Postgres on GCP — without changing this file:

```python
from skaal import App, Map

app = App("todos")

@app.storage(read_latency="< 10ms", durability="strong", throughput="> 100 rps")
class Todos(Map[str, dict]):
    pass
```

Run `skaal plan --explain` and the choice is auditable, not magic:

```text
Storage.Todos     3 candidates evaluated
  > dynamodb      7ms p50    $0.018/wu     selected
  - postgres     12ms p50    $0.024/wu     rejected: cost
  - sqlite        5ms p50    $0            rejected: throughput < 100 rps
```

[Back to top](#top)

## How It Differs

| | Skaal | Encore | SST | Wing | Pulumi alone |
|---|---|---|---|---|---|
| Language | Python | Go / TS | TS | Wing DSL | Any |
| Infra model | Constraint solver picks backend | Resource primitives | AWS resource bindings | Cloud-portable DSL | Imperative IaC |
| Backend choice | Solved per-environment from a catalog | Code-defined | Code-defined | Code-defined | Code-defined |
| Deploy mechanism | Generated Pulumi programs | Encore platform | CDK / CloudFormation | Terraform / CDK | Pulumi |
| Lock-in | Generated artifacts are yours; eject anytime | Platform-coupled | AWS-leaning | Compiler-coupled | None |
| License | GPL-3.0-or-later | MPL-2.0 | MIT | MIT | Apache-2.0 |

The differentiator is the **catalog + solver**. Other frameworks make you choose the backend in code; Skaal lets you describe what the backend must *do*, then re-solves when the environment (or its prices) change.

[Back to top](#top)

## Quickstart

```bash
pip install "skaal[serve]"
skaal init demo && cd demo
pip install -e .
skaal run
```

Add `runtime` if you need schedules, JWT auth, background jobs, or telemetry hooks:

```bash
pip install "skaal[serve,runtime]"
```

For HTTP, mount FastAPI, Starlette, or Dash and invoke Skaal compute from your handlers.

[Back to top](#top)

## How It Works

1. **Declare** constraints with decorators (`@storage`, `@compute`, `@blob`, `@scale`).
2. **Plan** against a TOML catalog with the Z3 solver — output is `plan.skaal.lock`.
3. **Build** target artifacts (Dockerfile, entrypoint, Pulumi program).
4. **Deploy** to local, AWS, or GCP via the generated Pulumi stack.

```bash
skaal plan   --app myapp:app --catalog catalogs/local.toml
skaal build  --app myapp:app --target local --catalog catalogs/local.toml
skaal deploy --app myapp:app --target local --catalog catalogs/local.toml
```

Generated artifacts land under `artifacts/` and are checked-in friendly. You can stop using Skaal at any time and keep the Pulumi output. See [docs/faq](https://elouen-ginat.github.io/Skaal/faq/) for the eject path.

[Back to top](#top)

## Platform Features

- **Storage tiers:** `Map[K, V]`, `Collection[T]`, `BlobStore`, relational (SQLModel + Alembic), vector.
- **Backends:** SQLite, Postgres, Redis, DynamoDB, Firestore, S3, GCS, Chroma, pgvector.
- **Compute & runtime:** async-first, ASGI/WSGI mounts, schedules, retries, rate limits, circuit breakers.
- **Channels:** local, Redis Streams, SNS/SQS — with EventLog, Outbox, Saga patterns.
- **Deployment:** generated Pulumi programs for local Docker, AWS Lambda, GCP Cloud Run.
- **Extensibility:** entry-point plugin model for backends and channels.

Full surface: [Platform Features](https://elouen-ginat.github.io/Skaal/platform-features/).

[Back to top](#top)

## Installation

```bash
pip install skaal                       # base
pip install "skaal[serve,runtime]"      # local development
pip install "skaal[deploy,aws,runtime]" # AWS
pip install "skaal[deploy,gcp,runtime]" # GCP
```

Other extras: `vector`, `fastapi`, `dash`, `examples`, `mesh`, `secrets-aws`, `secrets-gcp`. Full list in [docs/installation](https://elouen-ginat.github.io/Skaal/getting-started/).

[Back to top](#top)

## Examples

`examples/` contains: hello world, todo API, FastAPI streaming, file upload, Dash app, mesh counter, task dashboard, team directory.

[Back to top](#top)

## When Skaal Isn't a Fit

- You already maintain a mature Terraform / CDK monorepo and don't want a second IaC pipeline.
- Your stack relies on backends Skaal's catalog doesn't model (Kafka, Spanner, Cosmos DB, etc. — not yet).
- You need production-grade GCP today. Local and AWS targets are the most mature; GCP and the vector tier are still maturing.

[Back to top](#top)

## Project Status

**Alpha (0.3.1).** The core direction is stable: constraint declaration, Z3 planning, generated deployment, local + cloud execution from one codebase. Local + AWS targets are the most exercised; GCP, vector, and the Rust `mesh/` runtime are in active development. Public APIs (decorators in `skaal.decorators`, types in `skaal.types`) follow keyword-only-additive evolution; breaking changes go through ADRs in [`docs/design/`](docs/design).

Roadmap and design decisions: [ADR index](docs/design).

## Documentation & FAQ

- [Documentation home](https://elouen-ginat.github.io/Skaal/)
- [Getting started](https://elouen-ginat.github.io/Skaal/getting-started/)
- [Tutorials](https://elouen-ginat.github.io/Skaal/tutorials/)
- [How it works](https://elouen-ginat.github.io/Skaal/how-it-works/)
- [Catalogs](https://elouen-ginat.github.io/Skaal/catalogs/)
- [Comparison with other tools](https://elouen-ginat.github.io/Skaal/comparison/)
- [FAQ](https://elouen-ginat.github.io/Skaal/faq/)
- [Python API reference](https://elouen-ginat.github.io/Skaal/reference/python-api/)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and the [FAQ entry on GPL and SaaS use](https://elouen-ginat.github.io/Skaal/faq/#license).
