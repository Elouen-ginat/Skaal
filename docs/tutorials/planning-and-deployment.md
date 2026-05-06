# Tutorial 3: Plan, Build, and Deploy

At this point you have an app model. Now you can use Skaal for the thing it is built around: solving the cheapest valid infrastructure path for that model and generating artifacts from the result.

## What You Will Learn

- how catalogs shape the solver's search space
- what `plan.skaal.lock` is for
- how `skaal build` and `skaal deploy` consume the plan instead of re-reading your code from scratch

## Start With a Catalog

Before you solve anything, inspect the available backends:

```bash
skaal catalog validate catalogs/local.toml
skaal catalog browse --catalog catalogs/local.toml --section storage
skaal catalog sources catalogs/local.toml
```

That gives you three useful checks:

- the catalog parses and validates
- you can see which storage backends are actually available
- you can confirm the source chain for overlay catalogs

## Run `plan`

Solve your app against the local target:

```bash
skaal plan todo_api:app --target local --catalog catalogs/local.toml
```

This writes `plan.skaal.lock`. Treat that file as the resolved infrastructure contract for the current app, target, and catalog combination.

Look at it after the command runs. The important fields are:

- the deploy target
- the selected backend for each storage surface
- the selected compute shape, if any
- the source module that `skaal build` will use later

## Diff Before You Rebuild

Once a plan exists, use `skaal diff` to understand whether a change in code or catalog actually changes the resolved shape:

```bash
skaal diff
skaal diff todo_api:app
```

The first form prints the current plan summary. The second form re-solves and compares the fresh result against the plan already on disk.

## Build Artifacts From the Plan

Generate deployable output:

```bash
skaal build --out artifacts
```

For a local target, Skaal writes a Dockerfile, runtime entry point, Pulumi program, and stack metadata into `artifacts/`.

If you are developing Skaal itself and want the generated artifact to bundle your working tree instead of the published package, use:

```bash
skaal build --out artifacts --dev
```

## Deploy the Local Stack

```bash
skaal deploy --artifacts-dir artifacts
skaal infra status
```

The local deployment path is Pulumi-based, so `skaal deploy` brings up the generated stack and `skaal infra status` shows the active resources described by the current plan.

When you are done testing, tear it down again:

```bash
skaal destroy --artifacts-dir artifacts --stack local
```

## Retarget Without Rewriting the App

The main Skaal promise shows up here: the application model stays the same while the target changes.

```bash
skaal plan todo_api:app --target aws --catalog catalogs/aws.toml
skaal build --out artifacts
skaal deploy --artifacts-dir artifacts --stack prod
```

The code path is the same. The catalog and target are what change.

## A Good Project Setup

Inside a real project, put the default app reference in `pyproject.toml`:

```toml
[tool.skaal]
app = "todo_api:app"
target = "local"
catalog = "catalogs/local.toml"
```

That shortens the command loop considerably:

```bash
skaal run
skaal plan
skaal build
skaal deploy
```

## Reference Links

- Read [Python API: CLI-Parity API](../reference/python-api-cli-parity.md) for the `skaal.api` functions that mirror `run`, `plan`, `build`, `deploy`, and `diff`.
- Read [CLI Configuration](../cli-configuration.md) for full `tool.skaal` defaults, stack profiles, and supported `SKAAL_*` variables.

## Continue

Next: [Tutorial 4: Relational Data and Migrations](relational-and-migrations.md).
