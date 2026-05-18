# Tutorial 3b: Deploying to GCP

This tutorial walks you through deploying a small example app from this repository — `examples/counter_api.py` — to Google Cloud Run. By the end you will have a public URL that increments a counter stored in Firestore, and you will have torn the stack back down.

## What You Will Learn

- the one-time GCP setup you need before Skaal can deploy anything
- how `skaal doctor` tells you exactly what is missing
- how `skaal plan`, `skaal deploy`, and `skaal destroy` fit together
- that the same `App` graph can deploy to local, AWS, or GCP just by switching the env name

## The Example App

The app under `examples/counter_api.py` is intentionally tiny: one `Store[int]` and one mounted FastAPI route.

```python
from fastapi import FastAPI

from skaal import App, Store

app = App("counter-api")
api = FastAPI(title="Skaal Counter API")


@app.storage
class Counts(Store[int]):
    """Simple named counters."""


@app.expose()
async def increment(name: str = "world") -> dict[str, str | int]:
    count = (await Counts.get(name) or 0) + 1
    await Counts.set(name, count)
    return {"message": f"hello {name}", "count": count}


@api.get("/")
async def home(name: str = "world") -> dict[str, str | int]:
    return await increment(name=name)


app.mount("/", api)
```

On GCP this small app exercises the main cloud path:

- the `Store[int]` binds to Firestore
- the mounted FastAPI app binds to Cloud Run
- the public route stays thin and forwards to the Skaal-exposed function

## One-Time Setup

Skaal automates the Skaal-side glue (Pulumi config, image build, IAM, lock file) but a GCP deploy still has three external prerequisites you only need to do once.

### 1. Install the extras

```bash
pip install "skaal[serve,fastapi,deploy,gcp]"
```

### 2. Authenticate to GCP

The simplest option is Application Default Credentials:

```bash
gcloud auth application-default login
```

Alternatively, if you are deploying with a service account, export `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`.

### 3. Start Docker

Cloud Run runs a container image, so Skaal builds one locally during deploy. Start Docker Desktop (or `systemctl start docker` on Linux) and leave it running for the rest of the tutorial.

## Configure the Environment

Create `skaal.toml` at the repo root pointing at your GCP project:

```toml
[env.local]
target = "local"

[env.gcp]
target = "gcp"
region = "europe-west9"

[env.gcp.backends.gcp]
project = "skaal-test"
```

Pick any GCP project id you have access to; the rest of this tutorial assumes `skaal-test`.

## Verify Your Setup

```bash
skaal doctor --env gcp
```

You should see a green-ish output something like:

```text
Toolchain
┌────────────┬─────────────────────────────────────────────────────────┐
│ Python     │ 3.12.3                                                  │
│ Skaal      │ 0.4.0                                                   │
│ Pulumi CLI │ /usr/local/bin/pulumi                                   │
│ Docker     │ /usr/local/bin/docker (daemon up)                       │
└────────────┴─────────────────────────────────────────────────────────┘
Environment: gcp  (gcp)
┌─────────────┬─────────────────────────────────┐
│ region      │ europe-west9                    │
│ GCP project │ skaal-test (skaal.toml)         │
│ GCP auth    │ application-default-credentials │
└─────────────┴─────────────────────────────────┘
```

If any line is highlighted yellow, fix it before continuing:

- **Pulumi CLI: not on PATH** — install [Pulumi](https://www.pulumi.com/docs/install/).
- **Docker: daemon not running** — start Docker Desktop and re-run.
- **GCP project: not set** — your `[env.gcp.backends.gcp].project` entry is missing.
- **GCP auth: not detected** — re-run `gcloud auth application-default login`.

## Run the App Locally First

This is optional but a good sanity check:

```bash
skaal run examples.counter_api:app --env local
```

In another terminal:

```bash
curl "http://127.0.0.1:8000/?name=ada"
```

You should get `{"message": "hello ada", "count": 1}`. Hitting the endpoint again should return `count: 2`.

## Deploy to GCP

During the `0.4.0-alpha` Skaal is not yet published on PyPI, so the deploy command needs `--dev` to copy the local checkout into every container image. (Once `0.4.0` ships, drop the flag.)

```bash
skaal deploy examples.counter_api:app --env gcp --yes --dev
```

The first time you run this against a fresh project, Skaal will fail fast with a list of GCP APIs that need to be enabled — something like:

```text
ERROR   GCP project 'skaal-test' is missing required APIs for this deploy. Enable them with:

  gcloud services enable serviceusage.googleapis.com compute.googleapis.com run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com firestore.googleapis.com --project=skaal-test
```

Copy-paste that command, wait a few seconds, then re-run `skaal deploy`. From then on the deploy proceeds in one shot:

1. renders the build tree to `.skaal/build/gcp/` (Dockerfile, entrypoint, Pulumi program)
2. selects or creates a Pulumi stack named `counter-api-gcp`
3. builds the container image and pushes it to Artifact Registry
4. creates the Firestore database, service account, IAM bindings, and Cloud Run service
5. pins the chosen bindings into `skaal.lock`

On success Skaal prints the public URL as a stack output:

```text
Stack outputs:
  public_url = https://counter-api-xyz-uc.a.run.app
```

## Verify the Live App

```bash
curl "https://counter-api-xyz-uc.a.run.app/?name=ada"
curl "https://counter-api-xyz-uc.a.run.app/?name=ada"
```

The second call should return a higher `count` than the first, confirming both the public Cloud Run path and the Firestore-backed state are working.

## Inspect From Skaal

You do not need to leave the CLI to see what Skaal deployed:

```bash
skaal map examples.counter_api:app --env gcp
skaal where examples.counter_api:Counts examples.counter_api:app --env gcp
```

- `skaal map` prints the bound resource graph (and writes `.skaal/map.json`).
- `skaal where` resolves a primitive to the GCP console URL for the deployed resource.

## Tear It Down

```bash
skaal destroy examples.counter_api:app --env gcp --yes
```

This re-renders the build tree, selects the existing Pulumi stack, destroys every GCP resource Skaal created, and removes the stack record. It does **not** delete:

- `skaal.lock` — keep this so a re-deploy gets the same bindings
- `.skaal/` — the rendered artefacts and Pulumi state

If you want a truly clean slate, delete both manually.

!!! note "Firestore database deletion reservation"

    GCP keeps a deleted Firestore database id reserved for ~5 minutes after destroy. If you tear down and immediately re-deploy, the next `skaal deploy` may fail with `Database ID '...' is not available in project '...'. Please retry in N seconds.` — wait the suggested cool-down, then re-run.

## How Skaal Made This Simple

A few things that would normally require manual setup are handled for you:

- **Pulumi state**: on first deploy, Skaal writes Pulumi state to `./.skaal/pulumi-state/` (a project-local file backend) so you do not have to `pulumi login`. Set `PULUMI_BACKEND_URL` if you want state in S3/GCS/Pulumi Cloud instead.
- **Pulumi passphrase**: defaulted to empty since the local backend does not encrypt. Set `PULUMI_CONFIG_PASSPHRASE` yourself if you switch to an encrypted backend.
- **GCP API check**: Skaal queries Service Usage *before* invoking Pulumi and prints a single `gcloud services enable …` command instead of letting you hit one API error at a time.
- **Docker daemon check**: a missing or stopped daemon fails fast with one line, not 40 lines of Pulumi diagnostics.
- **Docker → Artifact Registry auth**: Skaal runs `gcloud auth configure-docker <region>-docker.pkg.dev` automatically before the image build, so you never see `denied: Unauthenticated request`.
- **Regional consistency**: Artifact Registry repositories and Firestore databases inherit the active environment's region, so cross-region egress and slow cold-starts are off by default.
- **Public Cloud Run service**: ASGI services get an `allUsers` invoker binding by default so the printed `public_url` works on `curl` without additional IAM steps.

## What This Does Not Cover

- custom domains, VPC networking, or Cloud SQL-backed services
- advanced GCP target overrides under `[env.<name>.backends.gcp.options]`
- production-grade Pulumi backends (Cloud, S3, GCS) — set `PULUMI_BACKEND_URL` to opt in

## Reference Links

- [CLI commands](../cli.md) — the exact command shapes for every verb.
- [Configuring your environments](../cli-configuration.md) — the full `skaal.toml` schema.
- [Python API: CLI-Parity API](../reference/python-api-cli-parity.md) — in-process equivalents for these commands.

## Continue

Next: [Tutorial 4: Relational data](relational-and-migrations.md).
