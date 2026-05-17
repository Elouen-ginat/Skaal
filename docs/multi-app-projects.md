# Multi-App Projects

A real codebase often ships more than one Skaal `App`. A backend service
plus a Dash frontend, an API plus a worker, a public app plus an
internal dashboard — they live in one repo, share one CI pipeline, and
deploy together.

Skaal models this as a *project* of cooperating apps:

- declared once under `[tool.skaal.apps]` in `pyproject.toml`,
- ordered by their declared `depends_on` edges,
- wired together at runtime through `AppRef`, with cross-app URLs
  injected automatically.

A single `skaal deploy --all` plans, builds, and deploys every app in
topological order. A single `skaal run --all` starts each app on its
own local port. `AppRef("backend")` in a downstream app resolves to
the backend's URL without any extra configuration.

## When to use it

- You have two or more `App`s that must deploy together.
- One app calls another via `AppRef`, and you don't want to hand-manage
  `BACKEND_URL` env vars.
- You want a single command for a clean dev loop and a single command
  for ship.

If your apps are independent, you don't need this — keep using
`[tool.skaal] app` and one-off `skaal deploy` runs. If you want to
collapse two apps into one process, use `Module` and `app.use(module)`
instead.

## Declare the apps

```toml
# pyproject.toml
[tool.skaal]
target  = "gcp"
catalog = "catalogs/gcp.toml"

[tool.skaal.apps.backend]
module = "myproject.backend:app"

[tool.skaal.apps.frontend]
module     = "myproject.frontend:app"
depends_on = ["backend"]
```

Each app entry takes one required field — `module`, the
`MODULE:VARIABLE` reference Skaal already understands — plus optional
overrides for the global `[tool.skaal]` keys (`target`, `region`,
`catalog`, `stack`, `gcp_project`, `out`, `env`, `pre_deploy`,
`post_deploy`, …) and the multi-app-specific keys covered below.

`depends_on` lists the names of upstream apps in the same `apps` table.
Cycles are caught at parse time. References to apps that don't exist
are rejected by `skaal apps validate`.

## Reference upstreams with `AppRef`

In the consumer app, declare an `AppRef` with just the upstream's name:

```python
from skaal import App, AppRef

app = App("frontend")
backend = AppRef("backend")    # name only — no base_url needed
app.attach(backend)

# Later:
result = await backend.create_task(id="42", title="ship it")
```

When the URL is auto-resolved (no `base_url=` or `base_url_secret=`),
`AppRef.call` automatically composes the canonical Skaal endpoint:

```text
{SKAAL_APPREF_BACKEND_URL}/_skaal/invoke/create_task
```

So you do not need to remember to append `/_skaal/invoke` yourself.

## Three resolution modes for `AppRef`

| Mode | How the URL gets there |
| --- | --- |
| Local dev (`skaal run --all`) | The orchestrator picks ports, writes `.skaal/local-endpoints.json`, and sets `SKAAL_APPREF_<NAME>_URL` on each consumer. |
| Multi-app deploy (`skaal deploy --all`) | The orchestrator captures each upstream's deploy URL, sets `SKAAL_APPREF_<NAME>_URL` on the consumer, and records the URL in `plan.skaal.project.lock`. |
| Manual / single-app deploy | Pass `base_url=` or `base_url_secret=` explicitly, the way you always could. Explicit values still win over the auto fallback. |

The default exposed env var is `SKAAL_APPREF_<NAME>_URL` (uppercased,
dashes replaced with underscores). Override it with `expose = "..."` on
the upstream's app entry. Set `endpoint_secret = "..."` to route the
URL through the secrets backend instead of plain env injection.

## Local dev: `skaal run --all`

```bash
skaal run --all
```

What happens:

1. Build a `ProjectGraph` from `[tool.skaal.apps]`.
2. Allocate a free port for every app starting at `--port` (default
   `8000`, then `+50` per app).
3. Write `.skaal/local-endpoints.json`:

   ```json
   {
     "backend":  "http://127.0.0.1:8000",
     "frontend": "http://127.0.0.1:8050"
   }
   ```

4. Spawn each app in a child process with `SKAAL_APPREF_<NAME>_URL`
   set for every upstream it depends on.
5. Tail child logs with a `[<app_name>]` prefix.

`skaal run frontend` (no `--all`) reads the registry too, so you can
keep one terminal running everything and restart just the frontend in
another — `AppRef("backend")` stays resolved.

## Cloud deploy: `skaal deploy --all`

```bash
skaal deploy --all --stack prod
```

The orchestrator walks the topological order:

1. Plans + builds + deploys each upstream, captures its service URL
   (Cloud Run / API Gateway URL) into `<artifacts>/<app>/url.txt`.
2. Sets `SKAAL_APPREF_<NAME>_URL` on each downstream consumer before
   running its plan/build/deploy.
3. After every successful step, updates `plan.skaal.project.lock` so
   later partial deploys can read upstream URLs without redeploying.

A failure mid-graph aborts the run and exits non-zero. Already-deployed
apps stay up; downstream apps are not touched. `skaal destroy --all`
reverses the order.

## Iterate on one app: `skaal deploy <name>`

```bash
skaal deploy frontend --stack prod
```

`skaal deploy <name>` and `skaal plan <name>` / `skaal build <name>`
operate on a single app from the project graph. Upstream URLs come
from `plan.skaal.project.lock`, so the backend doesn't redeploy
unless you ask it to. If a needed upstream has no recorded URL yet,
the command tells you to run `skaal deploy <upstream>` or
`skaal deploy --all` first.

The same pattern applies to `skaal run <name>` — it reads
`.skaal/local-endpoints.json` for upstream URLs so a local frontend
can call a previously-started backend without restarting it.

## Inspect the project: `skaal apps`

```bash
skaal apps                  # alias for `skaal apps list`
skaal apps list             # table of apps + last-deployed URL + stack
skaal apps list --json      # same data as JSON for scripts
skaal apps graph            # ASCII tree of the DAG
skaal apps graph -f dot     # Graphviz DOT (pipe to `dot -Tpng`)
skaal apps graph -f mermaid # mermaid markdown for docs
skaal apps validate         # cycle / undeclared / orphan-AppRef checks
```

`validate` does three things:

1. Catches cycles in `depends_on` (also caught lazily on every
   command that builds the graph).
2. Errors when `depends_on` lists an app that's not declared.
3. Imports each app module and warns when an `AppRef("X")` inside it
   points at a name that is not in `[tool.skaal.apps]`. That is
   sometimes intentional (the `AppRef` may target a third-party
   service), but it's the case where the orchestrator can't help you.

## Per-app artifact directories

When `--all` or `<app_name>` is used, each app writes to
`artifacts/<app_name>/` instead of `artifacts/`. Each per-app directory
contains the usual `plan.skaal.lock`, `Dockerfile`, generated
entrypoint, plus a `url.txt` written after a successful deploy.

Override the per-app dir with `out = "..."` on the app entry:

```toml
[tool.skaal.apps.frontend]
module = "myproject.frontend:app"
out    = "build/frontend"
```

The single-app commands (without `--all` or an `<app_name>` arg) keep
writing to `artifacts/` for backward compatibility.

## Project lock file

`plan.skaal.project.lock` is a small TOML file at the project root
written after each successful deploy. Example:

```toml
version = 1
updated_at = "2026-05-08T12:34:56+00:00"

[apps.backend]
module      = "myproject.backend:app"
target      = "gcp"
last_deploy = "2026-05-08T12:34:56+00:00"
last_url    = "https://backend-abc.run.app"
plan_lock   = "artifacts/backend/plan.skaal.lock"

[apps.frontend]
module      = "myproject.frontend:app"
target      = "gcp"
depends_on  = ["backend"]
last_deploy = "2026-05-08T12:35:12+00:00"
last_url    = "https://frontend-def.run.app"
plan_lock   = "artifacts/frontend/plan.skaal.lock"
```

Two roles:

- **Discovery for partial deploys.** `skaal deploy <name>` reads it to
  find upstream URLs.
- **Cross-PR drift visibility.** `skaal apps list` shows last-deployed
  URLs and timestamps so you can see at a glance which apps are stale.

The file is meant to be checked in alongside per-app `plan.skaal.lock`
files when you want a deterministic record of what's deployed.

## Different targets per app

`AppRef` URLs are public HTTPS, so two apps can target different
clouds: a backend on AWS Lambda fronted by API Gateway and a frontend
on GCP Cloud Run inter-operate without configuration.

```toml
[tool.skaal.apps.backend]
module = "myproject.backend:app"
target = "aws"
region = "us-east-1"

[tool.skaal.apps.frontend]
module     = "myproject.frontend:app"
target     = "gcp"
region     = "europe-west1"
depends_on = ["backend"]
```

For private endpoints, set `endpoint_secret` on the upstream so its
URL flows through the configured secrets backend instead of plain
env injection.

## Per-app stack profiles

Stack profiles still apply per-app. Declare them under
`[tool.skaal.apps.<name>.stacks.<stack>]` to give each app its own
prod / dev settings:

```toml
[tool.skaal.apps.backend]
target = "gcp"

[tool.skaal.apps.backend.stacks.prod]
gcp_project = "myproj-prod"
region      = "europe-west1"
```

## Python API

Every CLI verb has a Python equivalent under `skaal.api`:

```python
from skaal import api

graph = api.project_graph()           # build the ProjectGraph
api.plan_all()                        # plan every app
api.build_all(dev=True)               # build every app
steps = api.deploy_all(yes=True)      # deploy every app, return per-app status
api.destroy_all()                     # destroy in reverse topo order

# Restrict to a subset of apps:
api.deploy_all(only=["backend"])
```

`deploy_all` returns a list of `OrchestrationStep` records describing
what happened per app, with a `success` bool and the captured URL or
error string.

## Worked example

See [`examples/04_fullstack_split`](https://github.com/Elouen-ginat/Skaal/tree/main/examples/04_fullstack_split)
for a complete two-app project (FastAPI-backed Skaal `App` plus a Dash
frontend), including `[tool.skaal.apps]` snippets and the orchestrator
flow.

## Failure modes

- **Cycle in `depends_on`** — caught at config parse time;
  `skaal apps validate` prints the cycle. Cannot deploy.
- **Mid-graph deploy failure** — orchestrator stops on first failure,
  leaves already-deployed apps up, returns non-zero, and prints the
  per-app status block. `skaal destroy --all` is the rollback hatch.
- **`AppRef` to undeclared app** — `skaal apps validate` warns at
  config time. At runtime, `AppRef._resolve_base_url` raises with the
  env-var name it expected so you can fix it manually.
- **Stale `plan.skaal.project.lock`** — `skaal deploy <name>` fails
  fast if `last_url` for an upstream is missing; the message tells
  you to run `skaal deploy <upstream>` or `--all` first.

## Related

- [CLI Configuration](cli-configuration.md) — full
  `[tool.skaal.apps.*]` schema.
- [CLI](cli.md) — `skaal apps`, `--all`, and `<app_name>` flags on
  the existing commands.
