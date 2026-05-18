# Skaal CLI

The current CLI surface in `0.4.0a0` is small and direct:

- `init`
- `run`
- `plan`
- `map`
- `where`
- `trace`
- `build`
- `deploy`
- `destroy`
- `stubs`
- `doctor`

Each command has one job. The app argument is always a dotted `module:attribute` reference such as `examples.todo_api:app`.

<div class="skaal-cli-grid">
    <a class="skaal-cli-card skaal-cli-card--setup" href="#skaal-init">
        <span class="skaal-cli-card__eyebrow">Bootstrap</span>
        <span class="skaal-cli-card__title"><code>skaal init</code></span>
        <p class="skaal-cli-card__desc">Project scaffold placeholder in the current alpha.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--run" href="#skaal-run">
        <span class="skaal-cli-card__eyebrow">Develop</span>
        <span class="skaal-cli-card__title"><code>skaal run</code></span>
        <p class="skaal-cli-card__desc">Run the app locally from the bound plan for one environment.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--plan" href="#skaal-plan">
        <span class="skaal-cli-card__eyebrow">Plan</span>
        <span class="skaal-cli-card__title"><code>skaal plan</code></span>
        <p class="skaal-cli-card__desc">Render the diff between the current app and <code>skaal.lock</code>.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--inspect" href="#skaal-map">
        <span class="skaal-cli-card__eyebrow">Inspect</span>
        <span class="skaal-cli-card__title"><code>skaal map</code></span>
        <p class="skaal-cli-card__desc">Print the source-to-resource tree and emit JSON.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--ship" href="#skaal-build">
        <span class="skaal-cli-card__eyebrow">Generate</span>
        <span class="skaal-cli-card__title"><code>skaal build</code></span>
        <p class="skaal-cli-card__desc">Render deploy artifacts from the bound plan.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--ship" href="#skaal-deploy">
        <span class="skaal-cli-card__eyebrow">Ship</span>
        <span class="skaal-cli-card__title"><code>skaal deploy</code></span>
        <p class="skaal-cli-card__desc">Render again, apply with Pulumi, then update <code>skaal.lock</code>.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--ship" href="#skaal-destroy">
        <span class="skaal-cli-card__eyebrow">Ship</span>
        <span class="skaal-cli-card__title"><code>skaal destroy</code></span>
        <p class="skaal-cli-card__desc">Render again, destroy the stack with Pulumi, then remove the stack record.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--inspect" href="#skaal-where-and-skaal-trace">
        <span class="skaal-cli-card__eyebrow">Inspect</span>
        <span class="skaal-cli-card__title"><code>skaal where</code> / <code>skaal trace</code></span>
        <p class="skaal-cli-card__desc">Jump from a resource id to its cloud URL or source location.</p>
    </a>
    <a class="skaal-cli-card skaal-cli-card--inspect" href="#skaal-stubs-and-skaal-doctor">
        <span class="skaal-cli-card__eyebrow">Support</span>
        <span class="skaal-cli-card__title"><code>skaal stubs</code> / <code>skaal doctor</code></span>
        <p class="skaal-cli-card__desc">Emit typed stub packages and verify the local toolchain.</p>
    </a>
</div>

## The Core Loop

For most projects, the day-to-day loop is:

```bash
skaal run examples.counter:app --env local
skaal plan examples.counter:app --env local
skaal map examples.counter:app --env local
skaal build examples.todo_api:app --env prod
skaal deploy examples.todo_api:app --env prod
skaal destroy examples.todo_api:app --env prod --yes
```

`skaal run` starts the local runtime. `skaal plan` renders the diff against `skaal.lock`. `skaal map` shows the bound resources. `skaal build` renders deploy artifacts. `skaal deploy` renders and applies them. `skaal destroy` tears the same stack back down.

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

`skaal init` exists as a command name, but the scaffolder is not implemented in the current alpha.

```bash
skaal init
```

What you see:

- An error explaining that the new scaffolder has not landed yet.

What gets written:

- Nothing.

Common failure:

- The command exits non-zero by design in `0.4.0a0`.

## Run Locally

### `skaal run`

<div class="skaal-cli-banner skaal-cli-banner--run">
    <span class="skaal-cli-banner__label">Develop</span>
    <code>skaal run</code>
    <p>Run the app locally for one named environment.</p>
</div>

Run a Skaal app locally:

```bash
skaal run examples.counter:app
skaal run examples.counter:app --env local
skaal run examples.counter:app --host 0.0.0.0 --port 9000
```

Key options:

| Flag | Meaning |
| --- | --- |
| `--env`, `-e` | Select an environment from `skaal.toml`. Defaults to `local`. |
| `--host`, `--port` | Bind the local server to a different address or port. |

What you see:

- A local server for the chosen environment.
- Log output from the runtime and mounted ASGI app.

What gets written:

- Nothing.

Common failures:

- Missing `module:attribute` target or an import error in the target module.
- `--env` names an environment that does not exist in `skaal.toml`.

## Inspect the bound plan

### `skaal plan`

<div class="skaal-cli-banner skaal-cli-banner--plan">
    <span class="skaal-cli-banner__label">Plan</span>
    <code>skaal plan</code>
    <p>Render the diff between the current app and <code>skaal.lock</code>.</p>
</div>

`skaal plan` loads the app, binds it to one environment, loads `skaal.lock`, and prints the changes.

```bash
skaal plan examples.counter:app --env local
skaal plan examples.todo_api:app --env prod --format github-markdown
```

Useful options:

| Flag | Meaning |
| --- | --- |
| `--env`, `-e` | Select an environment from `skaal.toml`. |
| `--format` | Output as a terminal table or GitHub-flavored Markdown. |

What you see:

- One row per planned change.
- The app fingerprint, current bound fingerprint, and deployed fingerprint header.

What gets written:

- Nothing.

Common failures:

- `skaal.lock` is missing or unreadable.
- `skaal.toml` exists but does not define the requested environment.

### `skaal map`

<div class="skaal-cli-banner skaal-cli-banner--inspect">
    <span class="skaal-cli-banner__label">Inspect</span>
    <code>skaal map</code>
    <p>Print the source-to-resource tree and emit a machine-readable map.</p>
</div>

```bash
skaal map examples.todo_api:app --env local
skaal map examples.todo_api:app --env prod --out .skaal/todo-map.json
```

What you see:

- A tree grouped by source file.
- Resource kind, backend, and region for each leaf.

What gets written:

- `.skaal/map.json` by default, or the file passed with `--out`.

Common failures:

- Same app import and environment lookup failures as `skaal plan`.

## Generate and Ship Artifacts

### `skaal build`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Generate</span>
    <code>skaal build</code>
    <p>Produce the artifact bundle that downstream deploy commands consume.</p>
</div>

`skaal build` binds the app for one environment and renders deploy artifacts.

```bash
skaal build examples.todo_api:app --env prod
skaal build examples.todo_api:app --env prod --out artifacts/prod
skaal build examples.todo_api:app --env prod --python-version 3.12
```

Key options:

| Flag | Meaning |
| --- | --- |
| `--env`, `-e` | Select an environment from `skaal.toml`. |
| `--out`, `-o` | Output directory for generated artifacts. |
| `--python-version` | Python version for the rendered base image. |

What you see:

- A count of rendered resource artifacts.
- The destination directory.

What gets written:

- `.skaal/build/<env>/` by default, or the path passed with `--out`.

Common failures:

- Invalid app target.
- Missing deploy extras for the chosen target.

### `skaal deploy`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Ship</span>
    <code>skaal deploy</code>
    <p>Deploy a previously built artifact directory by running the target-specific Pulumi workflow.</p>
</div>

`skaal deploy` renders the artifacts for one environment and then runs Pulumi through the Automation API.

For AWS targets, run `skaal doctor` before the first deploy. Skaal expects the Pulumi CLI, Docker CLI, and an AWS credential source visible through the normal AWS SDK chain.

```bash
skaal deploy examples.todo_api:app --env prod
skaal deploy examples.todo_api:app --env prod --preview
skaal deploy examples.todo_api:app --env prod --yes
```

Important options:

| Flag | Meaning |
| --- | --- |
| `--env`, `-e` | Select an environment from `skaal.toml`. |
| `--out`, `-o` | Override the render directory for this deploy. |
| `--preview` | Run `pulumi preview` instead of `pulumi up`. |
| `--yes`, `-y` | Apply without interactive confirmation. |
| `--lock` | Choose a non-default `skaal.lock` path. |

What you see:

- The render directory.
- Pulumi stack name and Pulumi output.
- Exported stack outputs after apply, such as `public_url` for a mounted HTTP app.
- A success marker when preview or apply completes.

What gets written:

- A render tree, as with `skaal build`.
- `skaal.lock` entries for new pins.

Common failures:

- Pulumi CLI or SDKs are not installed.
- Docker is not installed or not running.
- `skaal[deploy,aws]` or the relevant target extras are missing.
- AWS credentials resolve to the wrong account or no credentials are detected.
- You chose the wrong environment or target-specific backend options are missing.

### `skaal destroy`

<div class="skaal-cli-banner skaal-cli-banner--ship">
    <span class="skaal-cli-banner__label">Ship</span>
    <code>skaal destroy</code>
    <p>Destroy the deployed stack for one environment and remove the Pulumi stack record.</p>
</div>

`skaal destroy` renders the artifacts for one environment, selects the existing Pulumi stack, destroys it, and removes the stack itself.

```bash
skaal destroy examples.todo_api:app --env prod
skaal destroy examples.todo_api:app --env prod --yes
```

Important options:

| Flag | Meaning |
| --- | --- |
| `--env`, `-e` | Select an environment from `skaal.toml`. |
| `--out`, `-o` | Override the render directory for this destroy run. |
| `--yes`, `-y` | Destroy without interactive confirmation. |
| `--lock` | Choose a non-default `skaal.lock` path for binding. |

What you see:

- The render directory.
- Pulumi stack name and destroy output.
- A success marker when the destroy completes.

What gets written:

- A render tree, as with `skaal build`.
- The Pulumi stack is removed after the destroy succeeds.

What stays behind:

- `skaal.lock`, unless you delete it yourself.

Common failures:

- Pulumi CLI or SDKs are not installed.
- The stack does not exist for the chosen app/environment.
- Cloud resources are protected or cannot be deleted with the current credentials.

## Locate or trace a resource

### `skaal where` and `skaal trace`

Use `where` to jump from a bound resource id to its cloud-console URL, and `trace` to jump from a resource id or log line back to the declaring source.

```bash
skaal where examples.todo_api:Comments examples.todo_api:app --env prod
skaal trace "examples.todo_api:Comments" examples.todo_api:app --env prod
```

What you see:

- `where`: stack name, provider type, physical id, and console URL.
- `trace`: matched text, source file and line, symbol, bound backend, and region.

What gets written:

- Nothing.

Common failures:

- The resource id does not exist in the bound plan.
- The environment does not match the deployed stack you are trying to inspect.

## Support commands

### `skaal stubs` and `skaal doctor`

`skaal stubs` emits a typed `.pyi` package for another Skaal app. `skaal doctor` checks that Python, Pulumi, Docker, and the Skaal package import cleanly, and it reports the visible AWS auth source for deploy troubleshooting.

```bash
skaal stubs --from examples.todo_api:app --to .stubs/todo_api
skaal doctor
```

What you see:

- `stubs`: the package name, destination, and resource count.
- `doctor`: Python version, Pulumi availability, Docker availability, AWS auth source and region, and Skaal version.

What gets written:

- `stubs`: the destination stub package.
- `doctor`: nothing.

Common failures:

- `stubs`: the `--from` target cannot be resolved.
- `doctor`: Skaal cannot import in the current environment.

## Related

- Read [Configuring your environments](cli-configuration.md) for `skaal.toml`, `[tool.skaal]`, and `SKAAL_*` resolution.
- Read [Python API: CLI-Parity API](reference/python-api-cli-parity.md) for the in-process equivalents.
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
