# 04 — Fullstack split (two Skaal apps)

A two-process example that mirrors a realistic deployment topology, with
**both sides being Skaal apps**:

```
+----------------------------------+   AppRef (HTTP/JSON)   +----------------------------------+
|  fullstack-frontend (Skaal App)  |  ───────────────────►  |  fullstack-backend (Skaal App)   |
|    + Dash UI via mount_wsgi      |                        |    + Store[Task]                 |
|    + AppRef -> backend           |                        |    + @app.function business logic|
|    + @app.function retry wrapper |                        |    + FastAPI mount_asgi (SSE)    |
+----------------------------------+                        +----------------------------------+
       :8050                                                          :8000
```

- [`backend.py`](backend.py) — a Skaal `App` with constraint-declared
  `Store[Task]` and `@app.function`s. The Skaal runtime auto-exposes every
  function at `/_skaal/invoke/<name>`, so other Skaal apps can call them
  via `AppRef` without writing any FastAPI routes. A small FastAPI router
  is mounted only for the streaming endpoint (which `AppRef` cannot
  consume — it is JSON-only).
- [`frontend.py`](frontend.py) — also a Skaal `App`. It owns no storage; it
  declares an `AppRef` pointing at the backend, wraps remote calls in
  `@app.function(retry=...)` so frontend-side resilience policies still
  apply, and mounts a Dash UI via `mount_wsgi`.

## Run locally

The shortest path is `skaal run --all` from a project that declares both
apps under `[tool.skaal.apps]` (see "Multi-app config" below). The
orchestrator picks ports for each app, writes
`.skaal/local-endpoints.json`, and injects `SKAAL_APPREF_BACKEND_URL`
into the frontend so `AppRef("backend")` resolves automatically:

```bash
pip install "skaal[serve,fastapi,examples]" dash dash-bootstrap-components httpx
skaal run --all
```

Then open [http://localhost:8050](http://localhost:8050).

To run the apps individually (no orchestrator), pass `BACKEND_URL`:

```bash
skaal run examples.04_fullstack_split.backend:app --port 8000
BACKEND_URL=http://localhost:8000 python examples/04_fullstack_split/frontend.py
```

Or repoint at any other backend host (e.g. a Cloud Run URL produced by
`skaal deploy --target gcp`) without editing code:

```bash
BACKEND_URL=https://backend-abc123.run.app python frontend.py
```

## Multi-app config

Add to your project's `pyproject.toml` so the two apps deploy and run as
a single project:

```toml
[tool.skaal]
target  = "gcp"
catalog = "catalogs/gcp.toml"

[tool.skaal.apps.backend]
module = "examples.04_fullstack_split.backend:app"

[tool.skaal.apps.frontend]
module     = "examples.04_fullstack_split.frontend:app"
depends_on = ["backend"]
```

Then:

```bash
skaal apps list           # show declared apps + last-deployed URL
skaal apps graph          # render the AppRef DAG
skaal run --all           # local dev: both apps + cross-app discovery
skaal deploy --all        # deploy backend, then frontend with URL injected
skaal deploy frontend     # iterate on the frontend; backend's URL is read
                          # from plan.skaal.project.lock
```

## How `AppRef` works

`AppRef("backend", base_url=...)` is an external component that turns
attribute access into HTTP POSTs. Calling `backend.create_task(id=..., title=...)`
issues `POST {base_url}/create_task`. The Skaal runtime exposes every
`@app.function` at `/_skaal/invoke/<name>`, so the frontend sets:

```python
backend = AppRef("backend", base_url=f"{BACKEND_HOST}/_skaal/invoke")
```

Wrapping the remote call in a local `@app.function(retry=...)` lets the
frontend layer apply its own retry/circuit-breaker policy on top of any
the backend already declares.

## Deploying both apps

`skaal deploy --all` walks the project graph in topological order:

1. Plans + builds + deploys the backend; captures its service URL
   (Cloud Run / API Gateway URL) into `<artifacts_dir>/url.txt` and the
   project lock.
2. Plans + builds + deploys the frontend with
   `SKAAL_APPREF_BACKEND_URL` set to the backend's URL, so the
   frontend's `AppRef("backend")` resolves automatically.
3. Writes `plan.skaal.project.lock` so `skaal deploy frontend` can
   later iterate on the frontend without redeploying the backend.

A failure mid-graph aborts and prints the structured status; already-
deployed apps stay up. `skaal destroy --all` reverses the order.

## What to try

1. Create a task in the UI — the Dash callback calls
   `app.invoke(create_task, ...)` which runs the local retry wrapper, which
   calls `backend.create_task(...)`, which is `AppRef.call("create_task")`,
   which POSTs to the backend's `/_skaal/invoke/create_task`.
2. Click "Stream" — the same UI, but this path bypasses `AppRef` and uses
   raw `httpx.stream` to consume the FastAPI SSE endpoint, since `AppRef`
   is JSON-only.
