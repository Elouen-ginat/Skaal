# Skaal CLI

The CLI follows the same shape as the framework itself: declare the app once, resolve a plan, then generate and deploy from that plan. The command surface is organized around that lifecycle instead of around individual cloud providers.

<div class="skaal-cli-grid">
    <a class="skaal-cli-card skaal-cli-card--setup" href="#skaal-init">
        <span class="skaal-cli-card__eyebrow">Bootstrap</span>
        <span class="skaal-cli-card__title"><code>skaal init</code></span>
        <p class="skaal-cli-card__desc">Scaffold a project and write the default app reference.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--run" href="#skaal-run">
        <span class="skaal-cli-card__eyebrow">Develop</span>
        <span class="skaal-cli-card__title"><code>skaal run</code></span>
        <p class="skaal-cli-card__desc">Run locally with reload, SQLite persistence, or Redis.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--plan" href="#skaal-plan">
        <span class="skaal-cli-card__eyebrow">Solve</span>
        <span class="skaal-cli-card__title"><code>skaal plan</code></span>
        <p class="skaal-cli-card__desc">Resolve backend choices and write <code>plan.skaal.lock</code>.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--plan" href="#skaal-diff">
        <span class="skaal-cli-card__eyebrow">Compare</span>
        <span class="skaal-cli-card__title"><code>skaal diff</code></span>
        <p class="skaal-cli-card__desc">Inspect how a fresh solve differs from the current plan.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--ship" href="#skaal-build">
        <span class="skaal-cli-card__eyebrow">Generate</span>
        <span class="skaal-cli-card__title"><code>skaal build</code></span>
        <p class="skaal-cli-card__desc">Create the artifact bundle from the locked plan.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--ship" href="#skaal-deploy">
        <span class="skaal-cli-card__eyebrow">Ship</span>
        <span class="skaal-cli-card__title"><code>skaal deploy</code></span>
        <p class="skaal-cli-card__desc">Apply the generated Pulumi stack for the resolved target.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--inspect" href="#skaal-catalog">
        <span class="skaal-cli-card__eyebrow">Inspect</span>
        <span class="skaal-cli-card__title"><code>skaal catalog</code></span>
        <p class="skaal-cli-card__desc">Browse, validate, and trace catalog layers before a solve.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--migrate" href="#skaal-migrate-relational">
        <span class="skaal-cli-card__eyebrow">Migrate</span>
        <span class="skaal-cli-card__title"><code>skaal migrate</code></span>
        <p class="skaal-cli-card__desc">Manage relational revisions and staged backend migrations.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--inspect" href="#skaal-apps">
        <span class="skaal-cli-card__eyebrow">Multi-App</span>
        <span class="skaal-cli-card__title"><code>skaal apps</code></span>
        <p class="skaal-cli-card__desc">List, graph, and validate the project's <code>[tool.skaal.apps]</code> DAG.</p>
    </a>
</div>

## The Core Loop

For most projects, the day-to-day command path is:

```bash
skaal init demo
cd demo
pip install -e .

skaal run
skaal plan demo.app:app --target local --catalog catalogs/local.toml
skaal build --out artifacts
skaal deploy --artifacts-dir artifacts
```

`skaal run` exercises the live app model. `skaal plan` writes `plan.skaal.lock`. `skaal build` reads that lock file and emits deployable artifacts. `skaal deploy` applies them.

## Global Flags

The root command supports logging controls that apply to every subcommand:

| Flag | Meaning |
| --- | --- |
| `-v`, `--verbose` | Increase log verbosity. `-v` gives INFO, `-vv` gives DEBUG. |
| `-q`, `--quiet` | Suppress INFO logs while still printing errors. |
| `--log-format text|json` | Switch between human-readable logs and machine-friendly JSON logs. |

## Bootstrap a Project

### `skaal init`

<div class="skaal-cli-banner skaal-cli-banner--setup">
    <span class="skaal-cli-banner__label">Bootstrap</span>
    <code>skaal init</code>
    <p>Scaffold a new Skaal project and set the default app reference in <code>pyproject.toml</code>.</p>
</div>

Use `skaal init` to scaffold a starter project and set `[tool.skaal] app` for you.

```bash
skaal init demo
skaal init demo --here
skaal init demo --force
```

The generated layout includes:

```text
demo/
├── pyproject.toml          # [tool.skaal] app = "demo.app:app"
├── README.md
├── .gitignore
├── catalogs/
│   └── local.toml
└── demo/
    ├── __init__.py
    └── app.py
```

The project name must be a valid Python identifier.

## Run Locally

### `skaal run`

<div class="skaal-cli-banner skaal-cli-banner--run">
    <span class="skaal-cli-banner__label">Develop</span>
    <code>skaal run</code>
    <p>Run the app locally with hot reload and switch between in-memory, SQLite, Redis, or the experimental mesh runtime path.</p>
</div>

Run a Skaal app locally with either an explicit `MODULE:APP`, the name of an entry under `[tool.skaal.apps]`, or the value from `[tool.skaal] app`.

```bash
skaal run examples.01_quickstart.app:app
skaal run examples.01_quickstart.app:app --persist
skaal run examples.01_quickstart.app:app --host 0.0.0.0 --port 9000

# Multi-app projects:
skaal run --all                # start every [tool.skaal.apps] entry on its own port
skaal run frontend             # one app from the project; reads cross-app URLs from
                               # .skaal/local-endpoints.json so AppRefs resolve
```

Key options:

| Flag | Meaning |
| --- | --- |
| `--host`, `--port` | Bind the local server to a different address or port. |
| `--all` | Start every app declared in `[tool.skaal.apps]`, one port each. Writes `.skaal/local-endpoints.json` so cross-app `AppRef`s resolve automatically. |
| `--persist` | Use SQLite-backed local persistence instead of in-memory storage. |
| `--db PATH` | Choose the SQLite file used with `--persist`. |
| `--redis URL` | Route supported storage through Redis for local testing. |
| `--reload`, `--no-reload` | Force hot reload on or off. |
| `--reload-dir PATH` | Add extra watched directories. Repeat the flag to watch multiple roots. |
| `--distributed --node-id NODE` | Experimental mesh runtime path. Requires `skaal[mesh]`. |

Reload defaults to automatic mode: on for interactive development, off for non-interactive or production-shaped environments.

## Solve and Inspect Plans

### `skaal plan`

<div class="skaal-cli-banner skaal-cli-banner--plan">
    <span class="skaal-cli-banner__label">Solve</span>
    <code>skaal plan</code>
    <p>Run the planner against a target and catalog, then lock the resolved infrastructure choices to disk.</p>
</div>

`skaal plan` runs the solver, resolves backend assignments, and writes `plan.skaal.lock`.

```bash
skaal plan examples.01_quickstart.app:app --target local --catalog catalogs/local.toml
skaal plan examples.04_fullstack_split.backend:app --target aws --catalog catalogs/aws.toml

# Multi-app projects:
skaal plan --all          # plan every [tool.skaal.apps] entry into its own
                          # artifacts/<name>/plan.skaal.lock in topo order
skaal plan backend        # plan one named app from [tool.skaal.apps]
```

Useful options:

| Flag | Meaning |
| --- | --- |
| `--target`, `-t` | Select the deploy target such as `local`, `aws`, `gcp`, or `aws-lambda`. |
| `--all` | Plan every app declared in `[tool.skaal.apps]` in topological order. |
| `--catalog PATH` | Use a specific catalog file instead of discovery or project defaults. |
| `--reoptimize` | Force re-solving all backend choices even when a lock file already exists. |
| `--pin NAME=BACKEND` | Pin one variable to a backend while investigating solver output. |

### `skaal diff`

<div class="skaal-cli-banner skaal-cli-banner--inspect">
    <span class="skaal-cli-banner__label">Compare</span>
    <code>skaal diff</code>
    <p>Compare the current plan with a freshly solved one before you rebuild or redeploy.</p>
</div>

Use `skaal diff` in two modes:

```bash
skaal diff
skaal diff examples.01_quickstart.app:app
```

Without an app argument it prints the current plan summary. With `MODULE:APP` it re-solves and shows what would change between the existing plan and the fresh one.

## Generate and Ship Artifacts

### `skaal build`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Generate</span>
    <code>skaal build</code>
    <p>Produce the artifact bundle that downstream deploy commands consume.</p>
</div>

`skaal build` reads the existing `plan.skaal.lock` and writes a self-contained `artifacts/` directory.

```bash
skaal build
skaal build --out artifacts
skaal build --out artifacts --stack prod --region eu-west-1
skaal build --dev

# Multi-app projects:
skaal build --all         # build artifacts/<name>/ for every [tool.skaal.apps] entry
skaal build frontend      # build one named app from [tool.skaal.apps]
```

Key options:

| Flag | Meaning |
| --- | --- |
| `--out`, `-o` | Output directory for generated artifacts. |
| `--all` | Build every app declared in `[tool.skaal.apps]`. Each app writes to `artifacts/<name>/` (or its `out` override) so multiple apps coexist on disk. |
| `--region`, `-r` | Override the region at build time. |
| `--stack`, `-s` | Resolve stack-specific settings from `[tool.skaal.stacks.<name>]`. |
| `--dev` | Bundle the local Skaal source tree into the artifact instead of relying on the published package. |

### `skaal deploy`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Ship</span>
    <code>skaal deploy</code>
    <p>Deploy a previously built artifact directory by running the target-specific Pulumi workflow.</p>
</div>

Deploy previously-built artifacts with Pulumi.

```bash
skaal deploy
skaal deploy --artifacts-dir artifacts --stack local
skaal deploy --artifacts-dir artifacts --stack prod --region eu-west-1

# Multi-app projects:
skaal deploy --all                 # plan + build + deploy every [tool.skaal.apps]
                                   # entry in topo order, injecting each upstream
                                   # URL into the next downstream's environment
skaal deploy frontend --stack prod # iterate on one app; upstream URLs come from
                                   # plan.skaal.project.lock
```

Important options:

| Flag | Meaning |
| --- | --- |
| `--all` | Deploy every app declared in `[tool.skaal.apps]` in topological order. Captures each upstream's service URL into `<artifacts>/<app>/url.txt` and `plan.skaal.project.lock`, then injects `SKAAL_APPREF_<NAME>_URL` for downstream apps. Aborts on the first failure. |
| `<app_name>` | Deploy a single app from `[tool.skaal.apps]`. Reads upstream URLs from `plan.skaal.project.lock` so the upstreams are not redeployed. |
| `--artifacts-dir`, `-a` | Directory created by `skaal build` (single-app mode only). |
| `--stack`, `-s` | Pulumi stack name. |
| `--region`, `-r` | Cloud region override. |
| `--gcp-project` | Required for GCP deploys when not already configured. |
| `--yes/--no-yes` | Control whether Pulumi runs non-interactively. |

### `skaal destroy`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Teardown</span>
    <code>skaal destroy</code>
    <p>Remove the Pulumi-managed resources for an artifact directory when you are done testing or shipping.</p>
</div>

Destroy the Pulumi-managed resources from an artifact directory.

```bash
skaal destroy --artifacts-dir artifacts --stack local
```

## Inspect Catalogs and Active Infra

### `skaal catalog`

<div class="skaal-cli-banner skaal-cli-banner--inspect">
    <span class="skaal-cli-banner__label">Inspect</span>
    <code>skaal catalog</code>
    <p>Browse the catalog, validate it, and inspect overlay source chains before you trust a solve.</p>
</div>

The `catalog` command group helps you inspect the solver input before or after you plan.

```bash
skaal catalog
skaal catalog browse --catalog catalogs/local.toml --section storage
skaal catalog validate catalogs/aws.toml
skaal catalog sources catalogs/aws.toml
```

Subcommands:

| Command | Purpose |
| --- | --- |
| `skaal catalog browse` | Print the resolved storage, compute, and network backends. |
| `skaal catalog validate` | Run the typed validators and exit non-zero on invalid catalogs. |
| `skaal catalog sources` | Show the `[skaal] extends` chain for overlay catalogs. |

### `skaal infra`

<div class="skaal-cli-banner skaal-cli-banner--inspect">
    <span class="skaal-cli-banner__label">Inspect</span>
    <code>skaal infra</code>
    <p>Show the active infrastructure described by the current plan and clean up migration state when needed.</p>
</div>

Inspect the resources described by the current plan and clean up migration state when needed.

```bash
skaal infra status
skaal infra cleanup --variable counter.Counts --yes
```

### `skaal stacks`

<div class="skaal-cli-banner skaal-cli-banner--inspect">
    <span class="skaal-cli-banner__label">Profiles</span>
    <code>skaal stacks</code>
    <p>List configured stack profiles and the resolved target, region, and protection settings for each one.</p>
</div>

List the stack profiles defined under `[tool.skaal.stacks.<name>]` in `pyproject.toml`.

```bash
skaal stacks
```

This is the quickest way to confirm which stack is current, which target each profile resolves to, and whether deletion protection or deploy hooks are enabled.

## Migrate Schemas and Backends

### `skaal migrate relational`

<div class="skaal-cli-banner skaal-cli-banner--migrate">
    <span class="skaal-cli-banner__label">Migrate</span>
    <code>skaal migrate relational</code>
    <p>Manage Alembic-backed schema revisions for SQLModel entities in Skaal's relational tier.</p>
</div>

This group manages Alembic-backed SQLModel migrations for the relational tier.

```bash
skaal migrate relational autogenerate -m "create todo comments"
skaal migrate relational upgrade
skaal migrate relational current
skaal migrate relational history
skaal migrate relational check
skaal migrate relational downgrade -1
skaal migrate relational upgrade --dry-run
```

Available subcommands:

| Command | Purpose |
| --- | --- |
| `autogenerate` | Compare registered models to the live database and create a revision. |
| `upgrade` | Apply migrations up to `head` or another target revision. |
| `downgrade` | Roll back to a target revision. |
| `current` | Show the applied revision per backend. |
| `history` | List every known revision and mark the current head. |
| `check` | Exit non-zero when drift exists between the live schema and the models. |
| `stamp` | Mark a revision without running SQL. |

These commands resolve the app from project settings, so they work best inside a scaffolded Skaal project or another project that already sets `[tool.skaal] app`.

### `skaal migrate data`

<div class="skaal-cli-banner skaal-cli-banner--migrate">
    <span class="skaal-cli-banner__label">Migrate</span>
    <code>skaal migrate data</code>
    <p>Advance or roll back staged backend migrations for storage variables while tracking discrepancies and progress.</p>
</div>

This group manages six-stage storage and channel backend migrations.

```bash
skaal migrate data start --variable counter.Counts --from redis --to dynamodb
skaal migrate data status --variable counter.Counts
skaal migrate data advance --variable counter.Counts
skaal migrate data rollback --variable counter.Counts
skaal migrate data list
```

Use it when you need to move a storage variable between backends while tracking shadow writes, discrepancies, and stage progression.

## Settings Resolution

Across the CLI, Skaal resolves settings in this order:

1. explicit CLI flags
2. `SKAAL_*` environment variables
3. `.skaal.env`
4. `[tool.skaal]` in `pyproject.toml`

That is why the scaffolded project is convenient: once `[tool.skaal] app` and optional stack settings are present, the daily command loop gets much shorter.

For a full `pyproject.toml` example, stack-profile guidance, logging config, and a complete list of supported `SKAAL_*` environment variables, read [CLI Configuration](cli-configuration.md).

## Experimental Mesh Runtime

`skaal run --distributed` exists, but the mesh runtime is still an experimental path. Treat it as an advanced reference surface, not as part of the default tutorial or deployment path.
