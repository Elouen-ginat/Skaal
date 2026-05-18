# Tutorial 3: Planning and deploying

At this point you have an app model and a local runtime. This tutorial adds named environments, deploy rendering, and the lock file.

## What You Will Learn

- how `skaal.toml` names environments
- what `skaal.lock` is for
- how `skaal plan`, `skaal map`, `skaal build`, and `skaal deploy` fit together

## Add `skaal.toml`

Create `skaal.toml` at the repo root:

```toml
[env.local]
target = "local"

[env.prod]
target = "aws"
region = "us-east-1"

[env.prod.backends.aws]
table_prefix = "prod-"
```

This gives Skaal two named environments:

- `local` for local runtime binding
- `prod` for AWS binding and deploy output

## Preview the plan

Use the existing example app for the rest of this tutorial:

```bash
skaal plan examples.todo_api:app --env local
```

What you see:

- one row per planned change between the current app and `skaal.lock`
- the bound environment and app fingerprints

What gets written:

- nothing. `skaal plan` is a diff command.

## Inspect the bound resources

```bash
skaal map examples.todo_api:app --env local
```

This prints the source-to-resource tree and writes `.skaal/map.json`.

## Render artifacts

Build the AWS-shaped artifact tree without touching cloud resources:

```bash
skaal build examples.todo_api:app --env prod
```

What you see:

- the number of rendered resource artifacts
- the output directory, which defaults to `.skaal/build/prod/`

What gets written:

- Dockerfiles
- runtime entrypoints
- Pulumi program files
- stack metadata for that environment

## Deploy

Install the deploy extras and make sure the Pulumi CLI is available:

```bash
pip install "skaal[deploy,aws]"
skaal doctor
```

Then deploy:

```bash
skaal deploy examples.todo_api:app --env prod --preview
skaal deploy examples.todo_api:app --env prod --yes
```

What you see:

- the render directory
- the Pulumi stack name
- preview or apply output

What gets written:

- a render tree, as with `skaal build`
- new entries in `skaal.lock` for resources that were pinned during deploy

## Why this matters

The app declaration did not change. You only added environment data and then ran different commands against different environment names.

That is the core Skaal trade:

- one app graph
- named environments in `skaal.toml`
- explicit lock pins in `skaal.lock`

## What this does not cover

- project scaffolding through `skaal init`
- advanced target-specific backend options
- teardown helpers beyond Pulumi itself

## Reference links

- Read [CLI commands](../cli.md) for the exact command shapes.
- Read [Configuring your environments](../cli-configuration.md) for the `skaal.toml` format.
- Read [Python API: CLI-Parity API](../reference/python-api-cli-parity.md) for the in-process equivalents.

## Continue

Next: [Tutorial 4: Relational data](relational-and-migrations.md).
