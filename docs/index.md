---
hide:
  - navigation
  - toc
---

<div class="skaal-hero">
  <div class="skaal-hero__copy">
    <p class="skaal-kicker">Infrastructure as Constraints for Python</p>
    <h1>Ship the app you want. Let Skaal choose the infrastructure that fits.</h1>
    <p class="skaal-lead">
      Skaal turns latency, durability, throughput, and deployment targets into declarative constraints.
      The solver finds the cheapest viable backend mix, then generates the runtime and deployment artifacts to run it.
    </p>
    <div class="skaal-hero__actions">
      <a class="md-button md-button--primary" href="getting-started/">Get Started</a>
      <a class="md-button" href="reference/python-api/">Browse Python API</a>
    </div>
    <div class="skaal-badge-row">
      <span class="skaal-chip">Python 3.11+</span>
      <span class="skaal-chip">Z3 Solver</span>
      <span class="skaal-chip">Local to Cloud</span>
      <span class="skaal-chip">AWS + GCP</span>
      <span class="skaal-chip">Pulumi Generated</span>
    </div>
  </div>
  <div class="skaal-hero__visual">
    <img src="design_system/components/plan-graph-example.svg" alt="Skaal plan graph showing the selected backend path." />
  </div>
</div>

## Why Skaal

Most frameworks force infrastructure choices into business code on day one. Skaal inverts that trade: you describe the behavior you need, and Skaal resolves an implementation strategy for the environment you are targeting.

<div class="grid cards" markdown>

- :material-tune: __Declare intent__

  Express latency, durability, throughput, scale, and access-pattern needs directly in Python.

- :material-graph-outline: __Solve infrastructure__

  Feed those constraints into a Z3-backed planner that scores available backends from a catalog.

- :material-source-branch-check: __Select the cheapest viable path__

  Keep alternatives visible while making the final route explicit and auditable.

- :material-file-code-outline: __Generate the deployment surface__

  Produce runtime entrypoints, Dockerfiles, Pulumi programs, and stack metadata for local or cloud targets.

</div>

## What You Get

<div class="skaal-showcase">
  <div class="skaal-showcase__panel">
    <img src="design_system/components/backend-card.svg" alt="Backend evaluation card example for DynamoDB." />
  </div>
  <div class="skaal-showcase__panel">
    <img src="design_system/components/pulumi-output.svg" alt="Generated Pulumi output example." />
  </div>
</div>

### Built for the full path from laptop to cloud

- Start local without rewriting the application later.
- Keep infrastructure selection outside business logic.
- Generate artifacts instead of hand-maintaining deployment glue.
- Move between local, AWS, and GCP using the same app model.
- Keep planning decisions explainable and cost-aware.

## Core Workflow

```python
from skaal import App, storage
from skaal.storage import Map

app = App("todo")


@storage(read_latency="< 10ms", durability="strong", throughput="> 100 rps")
class Todos(Map[str, dict]):
    pass
```

```bash
skaal plan --app myapp:app --catalog catalogs/local.toml
skaal build --app myapp:app --target local --catalog catalogs/local.toml
skaal deploy --app myapp:app --target local --catalog catalogs/local.toml
```

## Read the Docs by Outcome

<div class="grid cards" markdown>

- [Get started fast](getting-started.md)

  Installation, first app, and the shortest path to a running Skaal project.

- [Use the Python API](reference/python-api.md)

  In-process planning, building, deploying, and runtime entry points.

- [Work from the CLI](cli.md)

  Command-line planning, build, deploy, and local run flows.

- [Understand the HTTP model](http.md)

  How Skaal fits with FastAPI, Starlette, Dash, and ASGI patterns.

</div>
