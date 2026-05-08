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

In one terminal, start the backend:

```bash
pip install "skaal[serve,fastapi,examples]"
skaal run examples.04_fullstack_split.backend:app --port 8000
```

In a second terminal, start the frontend:

```bash
pip install dash dash-bootstrap-components httpx
python examples/04_fullstack_split/frontend.py
```

Then open [http://localhost:8050](http://localhost:8050).

Set `BACKEND_URL` to repoint at any other backend host (e.g. a Cloud Run
URL produced by `skaal deploy --target gcp`) without editing code:

```bash
BACKEND_URL=https://backend-abc123.run.app python frontend.py
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

Today, `skaal plan` / `skaal build` / `skaal deploy` operate on **one**
`App` per invocation, so deploying the pair is two `skaal deploy` runs
back to back with `BACKEND_URL` exported into the second one. The two
options that work today:

- Run them by hand, capturing the backend's URL after the first deploy
  and exporting `BACKEND_URL` before the second one.
- Use `[tool.skaal.stacks.<name>].pre_deploy` on the frontend's
  `pyproject.toml` to invoke `skaal deploy <backend>` and inject the
  backend URL into the frontend deploy environment.
- Or collapse both apps into one process by replacing the frontend `App`
  with a `Module` mounted via `app.use(module)` — single artifact, but
  loses the independent deploy / scale story.

A native multi-app project surface is being designed under
[ADR 028](../../notes/design/028-multi-app-projects-implementation-plan.md).
Once that lands, deploying both apps will be a single
`skaal deploy --all` driven by a `[tool.skaal.apps]` table, and the
`AppRef("backend")` lookup in the frontend will resolve to the backend's
deployed URL automatically.

## What to try

1. Create a task in the UI — the Dash callback calls
   `app.invoke(create_task, ...)` which runs the local retry wrapper, which
   calls `backend.create_task(...)`, which is `AppRef.call("create_task")`,
   which POSTs to the backend's `/_skaal/invoke/create_task`.
2. Click "Stream" — the same UI, but this path bypasses `AppRef` and uses
   raw `httpx.stream` to consume the FastAPI SSE endpoint, since `AppRef`
   is JSON-only.
