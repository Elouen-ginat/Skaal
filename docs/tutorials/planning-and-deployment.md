# Tutorial 3: Deploying a Simple AWS App

This tutorial is the smallest end-to-end AWS path that still feels like a real app: one HTTP route, one Skaal store, one named AWS environment, one deploy command that prints a stable public URL when it finishes, and one destroy command that tears the stack back down from inside Skaal.

## What You Will Learn

- how to keep the application logic inside Skaal while serving public HTTP
- which non-Skaal prerequisites AWS deploys still require
- how `skaal doctor`, `skaal plan`, `skaal deploy`, and `skaal destroy` fit together
- how `skaal.lock` records the bindings chosen on the first deploy

## Install the Extras

If you are starting from a blank environment, install the runtime, FastAPI, and AWS deploy extras together:

```bash
pip install "skaal[serve,fastapi,deploy,aws]"
```

## Create the App

Create `counter_api.py` at the project root:

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

This stays small, but it exercises the main AWS deploy path:

- one `Store[int]` that binds to DynamoDB in AWS
- one mounted ASGI app that binds to API Gateway + Lambda
- one public route that stays thin and forwards to the Skaal-exposed function

The repository copy of this tutorial app lives at `examples/counter_api.py` if you want a ready-made version to compare against.

## Add `skaal.toml`

Create `skaal.toml` at the repo root:

```toml
[env.local]
target = "local"

[env.prod]
target = "aws"
region = "us-east-1"
```

That is enough for this tutorial. No target-specific overrides are required.

## Prepare AWS Once

Skaal keeps the deploy flow simple, but AWS deploys still depend on a few external prerequisites:

- Pulumi CLI must be installed and on your `PATH`.
- Docker must be installed and running, because the AWS runtime is packaged as a Lambda container image.
- AWS credentials must resolve through the normal AWS SDK chain. The simplest setup is `aws configure` or an SSO-backed profile with `AWS_PROFILE` set in your shell.
- If Pulumi asks you to initialize its backend on the first run, complete `pulumi login` once and retry.

Skaal deploys into whichever AWS account and profile your shell currently resolves. Treat that account or profile as the project boundary for this tutorial.

Run the preflight check now:

```bash
skaal doctor
```

For an AWS deploy, the important lines are:

- `Pulumi CLI:` should point at a real executable.
- `Docker CLI:` should point at a real executable.
- `AWS auth:` should be `env`, `profile:<name>`, or `shared-config`.
- `AWS region:` can be empty here because this tutorial sets the region in `skaal.toml`.

If `AWS auth: not-detected` shows up, fix credentials before moving on.

## Check the App Locally

Run the app locally first:

```bash
skaal run counter_api:app --env local
```

In another shell, hit it once:

```bash
curl -s "http://127.0.0.1:8000/?name=ada"
```

You should get back a JSON payload with `message` and `count`.

## Preview the AWS Plan

Ask Skaal what it is about to bind and deploy:

```bash
skaal plan counter_api:app --env prod
skaal deploy counter_api:app --env prod --preview
```

What this does:

- `skaal plan` shows the lock diff for the AWS environment.
- `skaal deploy --preview` renders the build tree and runs `pulumi preview` without applying it.

For this app, the AWS side should be small and unsurprising:

- one DynamoDB table for `Counts`
- one Lambda function for the mounted ASGI service
- one API Gateway HTTP API in front of that function
- supporting resources such as an ECR repository, IAM role, and log group

## Deploy to AWS

When the preview looks right, apply it:

```bash
skaal deploy counter_api:app --env prod --yes
```

After a successful apply, Skaal now prints exported stack outputs in a stable format. For this tutorial app, the important one is `public_url`:

```text
Stack outputs:
  public_url = https://abcd1234.execute-api.us-east-1.amazonaws.com
```

What gets written during this step:

- `.skaal/build/prod/` with the rendered Dockerfile, entrypoint, Pulumi program, and stack files
- `skaal.lock` entries for the bindings chosen on the first deploy

## Verify the Live App

Use the printed `public_url` directly:

```bash
curl -s "<public_url>?name=ada"
curl -s "<public_url>?name=ada"
```

The second call should return a higher `count` than the first one, which confirms both the public HTTP path and the DynamoDB-backed state are working.

## Stay Inside Skaal After Deploy

You do not need to leave Skaal to inspect what it deployed:

```bash
skaal map counter_api:app --env prod
skaal where counter_api:Counts counter_api:app --env prod
```

- `skaal map` prints the bound resource graph and writes `.skaal/map.json`.
- `skaal where` resolves the `Counts` store to the deployed DynamoDB table's AWS console URL.

## Tear It Down From Skaal

When you are done with the tutorial stack, destroy it from the same Skaal app reference:

```bash
skaal destroy counter_api:app --env prod --yes
```

What this does:

- re-renders the same build tree Skaal used for deploy
- selects the existing Pulumi stack for `counter_api:app` in `prod`
- destroys the AWS resources and removes the Pulumi stack record

What it does not remove:

- `skaal.lock`, which still records the bindings chosen for this app
- `.skaal/build/prod/`, which is just the rendered artifact directory

## Why This Matters

The application code did not change between local and AWS. You only changed the environment name and let Skaal bind the same app graph to a different target.

That is the core deploy trade:

- one app graph
- one `skaal.toml` file naming environments
- one `skaal.lock` file recording resolved bindings

## What This Does Not Cover

- custom domains, VPC placement, or RDS-backed services
- advanced AWS target overrides under `[env.<name>.backends.aws.options]`

## Reference Links

- Read [CLI commands](../cli.md) for the exact command shapes.
- Read [Configuring your environments](../cli-configuration.md) for the `skaal.toml` format.
- Read [Python API: CLI-Parity API](../reference/python-api-cli-parity.md) for the in-process equivalents.

## Continue

Next: [Tutorial 4: Relational data](relational-and-migrations.md).
