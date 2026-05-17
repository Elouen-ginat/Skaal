# Concepts

These are the terms the rest of the docs use. If a page assumes one of them, come back here.

![Source to resource diagram](assets/graphics/diagrams/source-to-resource-arrow.svg)

## App

An **App** is the top-level Skaal declaration. It owns the storage classes, exposed functions, schedules, jobs, and mounted ASGI apps that make up one deployable unit.

```python
from skaal import App

app = App("billing")
```

## Module

A **Module** is a composable unit you can include inside an `App`. Use it when one app should be built from smaller, reusable pieces.

```python
from skaal import Module

payments = Module("payments")
```

## Data surfaces

`Store`, `Table`, `BlobStore`, and `Topic` are the typed primitives you declare in application code.

```python
@app.storage
class Users(Store[User]):
    pass


@app.storage(kind="blob")
class Uploads(BlobStore):
    pass
```

- `Store[T]` is typed key-value storage.
- `Table` is relational storage.
- `BlobStore` is object storage.
- `Topic[T]` is typed pub/sub.

## Blueprint

A **Blueprint** is the environment-independent shape of the app. Skaal infers it by walking the `App` graph.

```python
blueprint = app.blueprint()
```

The blueprint knows what resources exist and where they were declared. It does not know the final deploy backend yet.

## Plan

A **Plan** is the bound version of the blueprint for one environment. It includes concrete backends, regions, and deploy metadata.

```python
from skaal.api import load_plan

loaded = load_plan(app, env_name="prod")
bound_plan = loaded.bound
```

## Environment

An **Environment** is one `[env.<name>]` block in `skaal.toml`.

```toml
[env.local]
target = "local"

[env.prod]
target = "aws"
region = "us-east-1"
```

It tells Skaal which target you are binding for and any backend-specific options or overrides that apply there.

## Backend

A **Backend** is the concrete implementation behind a primitive. You can let Skaal choose from the environment, or you can type-pin the primitive.

```python
from skaal.backends.redis import Redis


@app.storage
class Sessions(Store[Session, Redis]):
    pass
```

## Binding

**Binding** is the step that combines the blueprint, one environment, and any existing lock entries into a concrete plan.

It is the point where a primitive such as `Store[Session]` becomes something deployable such as Redis, SQLite, or DynamoDB for one environment.

## Lock file

`skaal.lock` records per-environment pins for bound resources.

```toml
[entries.prod."examples.todo_api.Todos"]
backend = "dynamodb"
region = "us-east-1"
```

The lock file keeps later plan and deploy runs stable until the app or environment changes.

## Next

- Read [How it works](how-it-works.md) for the full pipeline.
- Read [Get started](getting-started.md) for the runnable version.
- Read [Python API](reference/python-api.md) for the concrete modules behind these terms.
