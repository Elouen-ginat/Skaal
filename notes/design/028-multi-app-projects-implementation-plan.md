# ADR 028 — Multi-App Projects and AppRef Resolution

**Status:** Proposed
**Date:** 2026-05-08
**Related:** [skaal/components.py](../../skaal/components.py) (`AppRef`), [skaal/settings.py](../../skaal/settings.py), [skaal/cli/deploy_cmd.py](../../skaal/cli/deploy_cmd.py), [skaal/cli/plan_cmd.py](../../skaal/cli/plan_cmd.py), [examples/04_fullstack_split](../../examples/04_fullstack_split), [ADR 022](022-catalog-overrides-implementation-plan.md)

## Goal

Let one `pyproject.toml` declare a *project* containing several Skaal
`App`s that reference one another via `AppRef`, and let a single
invocation of the CLI plan, build, and deploy the whole graph in
dependency order — with cross-app URLs wired automatically so
`AppRef("backend")` resolves at runtime without the user setting
`BACKEND_URL` themselves.

The user-facing shape is:

```toml
# pyproject.toml
[tool.skaal.apps.backend]
module = "myproject.backend:app"

[tool.skaal.apps.frontend]
module = "myproject.frontend:app"
depends_on = ["backend"]
```

```python
# myproject/frontend.py
from skaal import App, AppRef

app = App("frontend")
backend = AppRef("backend")    # name only — no base_url
app.attach(backend)
```

```bash
skaal deploy --all             # backend, then frontend, with URL injected
skaal deploy frontend          # just the frontend, reusing backend's last URL
skaal apps graph               # render the AppRef DAG
skaal run --all                # local dev: start every app on its own port
```

This closes the obvious gap that `examples/04_fullstack_split` exposes:
two Skaal apps that genuinely belong to one project, but today need
either a Makefile or a copy-pasted `pre_deploy` hook to deploy together.

## Why this is the right shape

1. **Users already think in projects.** A repo that ships `backend` plus
   `frontend` plus `worker` is one git repo, one CI pipeline, one
   `pyproject.toml`. Forcing each app to live in its own repo to get a
   sane deploy path is a tax on shape, not a property of the work.
2. **`AppRef` is already the cross-app calling primitive.** It is
   resolution that is missing — today `AppRef("backend")` requires the
   user to know the URL up front. A project graph is the natural
   resolution context: the URL is whatever `backend` emitted on its last
   deploy.
3. **Topological deploy is the rare case where Skaal needs to know about
   dependencies between apps.** Storage choice is per-app (the solver
   already handles it). Catalogs are per-app (ADR 022). Compute targets
   are per-app. The new thing here is *ordering between apps*.
4. **CI ergonomics.** A single `skaal deploy --all` exits non-zero if
   anything fails, prints a JSON status block, and tears down in reverse
   order on `skaal destroy --all`. That is what users expect from a
   multi-service tool today (Pulumi, Terraform Cloud, sst, serverless).

## Non-goals

- **Cross-app schema sharing / shared types.** Out of scope; users
  already share types via a Python package mounted into both apps.
- **Cross-target service mesh.** Apps may target different clouds in
  this design (backend on AWS, frontend on GCP), but Skaal does not try
  to configure VPC peering or private DNS between them. The wire format
  remains public HTTP plus signed/secret-protected URLs.
- **Hot-reload across apps.** `skaal run --all` starts each app under
  its own runtime; it does not synthesize a single asyncio loop or share
  storage handles. That is the `Module` story (`app.use(module)`).
- **Per-app stack profiles cross-product.** Stack profiles
  (ADR-prior `[tool.skaal.stacks.*]`) remain per-app, not per-project.
  A project-level stack would be the natural follow-up if users ask.

## Scope

This pass adds:

1. **`[tool.skaal.apps.<name>]` config.** A new top-level table in
   `pyproject.toml` declaring each app's `module` plus optional
   per-app overrides (`target`, `region`, `catalog`, `stack`,
   `depends_on`, `expose`, `endpoint_secret`, `pre_deploy`,
   `post_deploy`, `env`).
2. **`AppRef` graph resolution.** When `AppRef(name)` is constructed
   without `base_url=` or `base_url_secret=`, the runtime falls back
   to env var `SKAAL_APPREF_<NAME>_URL`. The deploy orchestrator and
   `skaal run --all` populate that env var from the producing app's
   deploy output / local port.
3. **`skaal apps` sub-app.**
   - `skaal apps list` — table of declared apps with their module,
     target, last-deployed URL, and status.
   - `skaal apps graph` — print the DAG (text by default, `--format=dot`
     and `--format=mermaid` for renderers).
   - `skaal apps validate` — check the DAG for cycles, undeclared
     `depends_on`, and `AppRef` names that point at apps not declared
     in the project.
4. **`--all` and `<app_name>` arguments on existing commands.**
   - `skaal plan [--all | <app_name>]`
   - `skaal build [--all | <app_name>]`
   - `skaal deploy [--all | <app_name>]`
   - `skaal destroy [--all | <app_name>]`
   - `skaal run [--all | <app_name>]`
   When neither is given, fall back to `[tool.skaal] app` for backward
   compat.
5. **Per-app artifact directories.** `skaal build` writes
   `artifacts/<app_name>/` instead of `artifacts/` when `--all` is used,
   so multiple apps coexist on disk.
6. **`plan.skaal.project.lock`.** A project-level lock file that
   records the topological order, the cross-app edges, and the
   last-deployed URL per app. `skaal deploy <app_name>` reads it to
   discover upstream URLs without re-deploying upstream apps.
7. **Local-dev endpoint registry.** `skaal run --all` writes
   `.skaal/local-endpoints.json` with `{<APP>: "http://localhost:<port>"}`
   so a separately-run `skaal run frontend` (without `--all`) picks up
   the backend's URL without explicit configuration.

This pass does **not** include:

- Shared infrastructure (a single Postgres backing two apps). The
  `[tool.skaal.shared]` design is sketched in §"Future work" but is
  out of scope. Users that need it today still mount a `Module` or
  pass an explicit DSN secret.
- Per-target deploy strategies *inside* one app (canary, blue/green).
  Orthogonal to multi-app orchestration.
- A web UI for the graph. CLI ASCII / DOT output is sufficient at this
  stage; a UI follows the docs site's design system if it ships.

## Design

### 1. Config: `[tool.skaal.apps.<name>]`

A new table per app, parsed alongside the existing `[tool.skaal]`
keys. The full schema:

```toml
[tool.skaal.apps.<name>]
module = "myproject.backend:app"     # required; MODULE:APP

# All optional, falling back to [tool.skaal] base values:
target       = "gcp"
region       = "europe-west1"
catalog      = "catalogs/gcp.toml"
stack        = "prod"
gcp_project  = "my-project"
out          = "artifacts/backend"   # default: artifacts/<name>
env          = { LOG_LEVEL = "info" }

# Multi-app specific:
depends_on       = ["other-app"]      # names from this same table
expose           = "BACKEND_URL"      # env var name consumers see (default: SKAAL_APPREF_<NAME>_URL)
endpoint_secret  = "BACKEND_URL"      # if set, expose via SecretRef instead of plain env

# Per-app deploy hooks (replace the project-wide ones, not append):
pre_deploy  = [["bash", "-c", "echo deploying backend"]]
post_deploy = [["python", "scripts/notify.py", "backend"]]
```

Resolution rules:

- `module` is the only required field.
- Every other field falls back to the corresponding `[tool.skaal]`
  value, then to the built-in default. So a project that targets one
  cloud globally can omit `target` / `catalog` per app.
- `depends_on` names must reference other entries in the same
  `[tool.skaal.apps]` table. Cycles are an error at parse time.
- `expose` defaults to `SKAAL_APPREF_<NAME>_URL` (uppercased, dashes
  to underscores). When `endpoint_secret` is set, the orchestrator
  registers it as a `SecretRef` on the consuming app instead of a
  plain env var, routing through the existing secrets backend.

Backward compat: `[tool.skaal] app = "..."` continues to work as the
single-app shortcut. If both `app` and `apps.*` are present, `apps`
wins and `app` is treated as a typo (a one-line warning at load time).

### 2. New types

`skaal/types/project.py` (new):

```python
@dataclass(frozen=True)
class AppNode:
    name: str
    module: str
    target: str | None
    region: str | None
    catalog: str | None
    stack: str | None
    out: Path
    env: Mapping[str, str]
    depends_on: tuple[str, ...]
    expose: str
    endpoint_secret: SecretRef | None
    pre_deploy: tuple[tuple[str, ...], ...]
    post_deploy: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ProjectGraph:
    apps: Mapping[str, AppNode]      # by name
    order: tuple[str, ...]           # topological deploy order
    edges: Mapping[str, frozenset[str]]   # consumer -> {producers}

    def upstreams(self, name: str) -> tuple[AppNode, ...]: ...
    def downstreams(self, name: str) -> tuple[AppNode, ...]: ...
    def expose_env_for(self, consumer: str) -> Mapping[str, str]: ...
```

Re-exported from `skaal.types`.

### 3. AppRef graph resolution

`AppRef._resolve_base_url` (today, in
[`skaal/components.py:491`](../../skaal/components.py)) gains a third
fallback after the literal `connection_string` and the explicit
`SecretRef`:

```python
def _resolve_base_url(self) -> str:
    if self.connection_string:
        return self.connection_string.rstrip("/")
    if self.secret is not None:
        url = os.environ.get(self.secret.env_var)
        if url:
            return url.rstrip("/")
    auto_var = f"SKAAL_APPREF_{self.name.upper().replace('-', '_')}_URL"
    auto_url = os.environ.get(auto_var)
    if auto_url:
        return auto_url.rstrip("/")
    raise RuntimeError(
        f"AppRef {self.name!r}: set base_url=, base_url_secret=, or the "
        f"{auto_var!r} env var (auto-injected by `skaal deploy --all` "
        f"and `skaal run --all`)."
    )
```

The auto env var is the only addition — both existing paths still win.
This means `AppRef("backend")` works in three modes:

| Mode | How the URL gets there |
| --- | --- |
| Local dev (`skaal run --all`) | Project orchestrator writes `.skaal/local-endpoints.json`; runtime reads it before starting consumer apps. |
| Multi-app deploy (`skaal deploy --all`) | Orchestrator captures upstream's deploy output and sets `SKAAL_APPREF_<NAME>_URL` on the consumer. |
| Manual / single-app deploy | User still sets `base_url=` or `base_url_secret=` explicitly. |

The runtime path for the auto var goes through whatever secrets
backend the consumer is configured with when `endpoint_secret` is set,
so URLs that need to be private (Cloud Run with IAM, Lambda with
private API Gateway) flow through the same path as DB DSNs.

### 4. CLI: `skaal apps`

`skaal/cli/apps_cmd.py` (new) — a typer sub-app:

```
skaal apps                       # alias for `skaal apps list`
skaal apps list [--json]         # table of apps + status
skaal apps graph [--format=ascii|dot|mermaid]
skaal apps validate              # cycle / undeclared-name / orphan-AppRef checks
```

`list` reads `[tool.skaal.apps]` and (if present)
`plan.skaal.project.lock` to show last-deployed URL and time.
`graph` walks `depends_on` and `AppRef` names from each app's module
import to render the DAG. Two sources of edges so the graph reflects
both *declared* dependencies and *observed* ones — divergence between
them is a warning surfaced in `apps validate`.

`validate` runs three checks:

1. `depends_on` references an app not in `[tool.skaal.apps]` → error.
2. Cycle in `depends_on` → error (with the cycle printed).
3. App imports an `AppRef("X")` whose name is not in the project →
   warning. (Could be intentional — pointing at a third-party
   service — but worth surfacing.)

### 5. CLI: `--all` / `<app_name>` arguments

The five commands that take `MODULE:APP` today (`plan`, `build`,
`deploy`, `destroy`, `run`) gain a new resolution order:

```
skaal deploy                     # if [tool.skaal] app set: that app (today's behavior)
skaal deploy --all               # NEW: every app in [tool.skaal.apps], topo order
skaal deploy backend             # NEW: app named in [tool.skaal.apps]
skaal deploy myproject.x:app     # explicit MODULE:APP (today's behavior)
```

Implementation:

1. Resolve a `ProjectGraph` from the merged settings.
2. If `--all`, iterate `graph.order` and run the existing per-app
   command in a subprocess (or in-process function call) per node.
   Capture each node's deploy output and set
   `SKAAL_APPREF_<NAME>_URL` for downstream nodes before invoking
   them.
3. If `<app_name>`, resolve to that single `AppNode`, then read
   `plan.skaal.project.lock` for upstream URLs and inject them into the
   environment before deploying just that node.
4. On any failure: print a structured status block, exit non-zero, do
   **not** continue to downstream nodes. `--continue-on-failure` is a
   future flag.

`skaal destroy --all` reverses `graph.order`. Mid-graph failure leaves
a partial state and prints what is still up.

### 6. Per-app artifact directories

`skaal build` today writes to `artifacts/`. Under multi-app:

- If `--all` or `<app_name>`, write to `artifacts/<app_name>/` so
  multiple apps coexist.
- Single-app, no project graph: keep `artifacts/` for back-compat.

Each per-app artifact dir contains `plan.skaal.lock`, `pyproject.toml`,
`Dockerfile`, the generated `main.py` / `handler.py`, and the
`url.txt` file that the orchestrator writes after deploy
(today's deploy step writes the URL to stdout — see §7).

### 7. `plan.skaal.project.lock`

A new project-level lock file written next to the per-app locks:

```toml
# plan.skaal.project.lock
version = 1
updated_at = "2026-05-08T12:34:56Z"

[apps.backend]
module = "myproject.backend:app"
target = "gcp"
last_deploy = "2026-05-08T12:34:56Z"
last_url = "https://backend-abc.run.app"
plan_lock = "artifacts/backend/plan.skaal.lock"

[apps.frontend]
module = "myproject.frontend:app"
target = "gcp"
last_deploy = "2026-05-08T12:35:12Z"
last_url = "https://frontend-def.run.app"
plan_lock = "artifacts/frontend/plan.skaal.lock"
depends_on = ["backend"]
```

Two roles:

- **Discovery for partial deploys.** `skaal deploy frontend` reads
  this file to find `last_url` for `backend` and inject it as
  `SKAAL_APPREF_BACKEND_URL` without redeploying the backend.
- **Cross-PR drift visibility.** `skaal apps list` and `skaal diff
  --all` use it to show which apps' source has changed since their
  last deploy.

### 8. Deploy output capture

Today the deploy CLI prints the service URL but does not capture it.
The orchestrator needs the URL programmatically. Two changes:

- `skaal deploy` writes `<artifacts_dir>/url.txt` (single line) after
  a successful deploy, regardless of whether `--all` was used. Pulumi
  outputs already carry the URL on AWS Lambda (API Gateway URL) and
  GCP Cloud Run (service URL); we read them via `pulumi stack output
  --json` after `pulumi up` finishes.
- The orchestrator reads `url.txt` for each upstream and exports it
  to the downstream's environment.

This keeps the in-process API simple: each per-app deploy stays a
single `pulumi up` invocation; the orchestrator is a thin shell that
sequences them and shuffles environment variables.

### 9. Local-dev endpoint registry

`skaal run --all`:

1. Compute `ProjectGraph`.
2. Pick a free port per app starting at `8000`, plus the requested
   `--port` for the first one if given.
3. Write `.skaal/local-endpoints.json`:

   ```json
   {"backend": "http://127.0.0.1:8000", "frontend": "http://127.0.0.1:8050"}
   ```

4. Spawn each app via the existing `LocalRuntime.serve` in a child
   process, with `SKAAL_APPREF_<NAME>_URL` set from the registry.
5. Tail logs with a `[<app_name>]` prefix.

`skaal run <name>` without `--all` also reads the registry, so a
developer can keep `skaal run --all` running in one terminal and
restart just the frontend in another — the backend URL is already
discovered.

### 10. Stack profiles

Stack profiles (`[tool.skaal.stacks.<stack>]`) layer over the
*resolved per-app* settings, not over the project settings. So:

```toml
[tool.skaal.apps.backend]
target = "gcp"

[tool.skaal.apps.backend.stacks.prod]
gcp_project = "myproj-prod"
region      = "europe-west1"
```

The prefix is per-app on purpose — different apps may want different
prod regions. A `[tool.skaal.project.stacks.<stack>]` for cross-app
defaults is a follow-up (see §"Future work").

## Files touched

- `skaal/settings.py` — extend `SkaalSettings` with an `apps:
  Mapping[str, AppSettings]` field and a `for_app(name)` resolver
  that merges base + apps + stack overlays.
- `skaal/types/project.py` (new) — `AppNode`, `ProjectGraph`, and a
  `build_project_graph(settings: SkaalSettings) -> ProjectGraph`
  helper that runs cycle / undeclared-name validation.
- `skaal/types/__init__.py` — export `AppNode`, `ProjectGraph`.
- `skaal/components.py` — extend `AppRef._resolve_base_url` with the
  `SKAAL_APPREF_<NAME>_URL` fallback. Update the docstring.
- `skaal/cli/apps_cmd.py` (new) — `skaal apps {list, graph, validate}`.
- `skaal/cli/_orchestrator.py` (new) — sequential deploy / destroy /
  run runner that consumes a `ProjectGraph` and shuffles env vars.
- `skaal/cli/deploy_cmd.py` — accept positional `<app_name>` and
  `--all`; on success write `<artifacts_dir>/url.txt`.
- `skaal/cli/plan_cmd.py`, `skaal/cli/build_cmd.py`,
  `skaal/cli/destroy_cmd.py`, `skaal/cli/run_cmd.py` — same
  positional / `--all` shape.
- `skaal/cli/main.py` — register `apps` sub-app.
- `skaal/api.py` — `project_graph()`, `deploy_all()`, `run_all()`
  helpers mirroring the CLI verbs (parity with ADR 020 / 021 pattern).
- `tests/cli/test_apps_cmd.py` (new) — `apps list` / `graph` /
  `validate` happy paths and error reports.
- `tests/cli/test_orchestrator.py` (new) — topological ordering,
  env-var injection, partial deploy reads from `plan.skaal.project.lock`.
- `tests/runtime/test_appref.py` — extend with the
  `SKAAL_APPREF_<NAME>_URL` resolution path.
- `tests/settings/test_apps_config.py` (new) — config parsing,
  resolution rules, stack overlays.
- `docs/multi-app-projects.md` (new) — the user-facing guide.
- `docs/cli-configuration.md` — document `[tool.skaal.apps.*]`.
- `docs/cli.md` — document `skaal apps` and the `--all` /
  `<app_name>` shape.
- `examples/04_fullstack_split` — drop the manual orchestration text
  in the README; show the `[tool.skaal.apps]` config and
  `skaal deploy --all`.

## Worked example — `examples/04_fullstack_split` after this lands

`pyproject.toml`:

```toml
[tool.skaal]
target  = "gcp"
catalog = "catalogs/gcp.toml"

[tool.skaal.apps.backend]
module = "examples.04_fullstack_split.backend:app"

[tool.skaal.apps.frontend]
module      = "examples.04_fullstack_split.frontend:app"
depends_on  = ["backend"]
expose      = "SKAAL_APPREF_BACKEND_URL"   # default; shown for clarity
```

`frontend.py`:

```python
from skaal import App, AppRef

app = App("frontend")
backend = AppRef("backend")    # name only; resolved by the orchestrator
app.attach(backend)
```

Local dev:

```bash
skaal run --all
# starts backend on :8000, frontend on :8050,
# writes .skaal/local-endpoints.json,
# frontend's AppRef("backend") resolves automatically.
```

Deploy:

```bash
skaal deploy --all --stack prod
# 1. plans + builds + deploys backend; captures Cloud Run URL.
# 2. plans + builds + deploys frontend with
#    SKAAL_APPREF_BACKEND_URL=https://backend-abc.run.app injected.
# 3. writes plan.skaal.project.lock for incremental redeploys.
```

Iterate on the frontend without redeploying the backend:

```bash
skaal deploy frontend --stack prod
# reads plan.skaal.project.lock → gets backend's last URL → deploys
# only the frontend with that URL injected.
```

## Failure modes and rollback

- **Cycle in `depends_on`** — caught at config parse time;
  `skaal apps validate` reports the cycle. Cannot deploy.
- **Mid-graph deploy failure** — orchestrator stops on first failure,
  leaves already-deployed apps up, returns non-zero, and prints the
  structured status. `skaal destroy --all` is the rollback hatch (it
  reverses the order). `--continue-on-failure` follows in a later
  pass.
- **`AppRef` to undeclared app** — `apps validate` warns at config
  time. At runtime, the resolver raises with the env-var name it
  expected so users can fix it manually.
- **Stale `plan.skaal.project.lock`** — `skaal deploy <name>` fails
  fast if `last_url` for an upstream is missing; the message tells
  the user to run `skaal deploy <upstream>` or `--all` first.
- **Different targets per app** — fully supported. The
  `SKAAL_APPREF_<NAME>_URL` mechanism is HTTP, so a backend on AWS
  Lambda fronted by API Gateway and a frontend on GCP Cloud Run
  interoperate without configuration. Private endpoints flow through
  `endpoint_secret` so the URL itself is not in plaintext env.

## Phased rollout

This ADR is one feature, but the implementation is naturally three
slices that can land independently:

1. **Phase 1 (P0).** Config parsing (`[tool.skaal.apps.*]`),
   `ProjectGraph`, `AppRef` env-var fallback, `skaal apps list /
   graph / validate`, `skaal deploy --all` with sequential
   orchestration and env injection. Closes the
   `examples/04_fullstack_split` story.
2. **Phase 2 (P1).** `plan.skaal.project.lock`, partial deploy
   (`skaal deploy <name>`), per-app artifact directories,
   `skaal destroy --all`, `skaal diff --all`.
3. **Phase 3 (P2).** `skaal run --all`, local-endpoint registry,
   per-app stack profiles (`[tool.skaal.apps.<name>.stacks.<stack>]`),
   `--format=mermaid` for the graph.

Each phase ships its own tests and docs and is independently
shippable.

## Future work

- **`[tool.skaal.shared.*]` shared resources.** A single Postgres or
  Redis backing several apps. Requires Pulumi to provision shared
  resources in a separate stack, export the connection details, and
  inject them as `SecretRef`s. Worth a follow-up ADR.
- **Project-level stack profiles.** `[tool.skaal.project.stacks.dev]`
  applying to every app at once. Useful for "everything dev runs in
  `eu-west1` against the dev catalog."
- **Service mesh / private endpoints.** For now `AppRef` URLs are
  public HTTPS. A later ADR can add VPC-internal addressing for AWS
  and Cloud Run with IAM-only invokers.
- **Cross-target migrations.** Moving `backend` from AWS to GCP
  while keeping the URL stable. The mesh migration story (ADR 004)
  could be lifted to the project level.
- **Web graph visualization.** A `skaal apps serve` command that
  renders the live DAG and per-app status in a browser.
- **Polyglot apps.** A non-Python `App` slot in `[tool.skaal.apps]`
  whose `module` points at a Dockerfile or a precompiled binary,
  exposing a Skaal-compatible `/_skaal/invoke/*` surface so
  `AppRef("backend")` from a Python frontend still works.

## References

- Today's `AppRef` implementation:
  [`skaal/components.py:458`](../../skaal/components.py).
- Today's settings model:
  [`skaal/settings.py`](../../skaal/settings.py).
- Today's deploy entry point:
  [`skaal/cli/deploy_cmd.py`](../../skaal/cli/deploy_cmd.py).
- Stack profiles overlay model: [ADR 022](022-catalog-overrides-implementation-plan.md)
  and [`docs/cli-configuration.md`](../../docs/cli-configuration.md#tool-skaal-stacks-name-keys).
- `Module` and `app.use(...)` (the single-process alternative):
  [`skaal/module.py:699`](../../skaal/module.py).
- Worked motivating example: [`examples/04_fullstack_split`](../../examples/04_fullstack_split).
