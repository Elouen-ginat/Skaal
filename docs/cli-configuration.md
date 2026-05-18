# Configuring your environments

Skaal has two configuration surfaces during the redesign:

- `skaal.toml` defines named environments for binding and deployment.
- `[tool.skaal]` in `pyproject.toml` still provides CLI defaults and logging configuration.

Use `skaal.toml` first. Use `[tool.skaal]` as the compatibility layer for command defaults.

## Resolution Order

For CLI defaults, Skaal resolves values in this order:

1. explicit CLI flags or Python keyword arguments
2. `SKAAL_*` environment variables
3. `.skaal.env`
4. `[tool.skaal]` in the nearest `pyproject.toml`
5. built-in defaults

For environments, Skaal resolves values from `skaal.toml` itself:

- `skaal plan/build/deploy/run/map/where/trace --env <name>` loads `[env.<name>]`
- if `skaal.toml` is missing, Skaal synthesizes one baseline environment named `local`

Two related behaviors sit beside the shared CLI settings:

- `SKAAL_LOG_FORMAT` and `SKAAL_LOG_LEVEL` affect CLI logging.
- `SKAAL_ENV` affects `skaal run` hot-reload auto mode and is treated as a runtime behavior flag rather than a normal structured setting.

## File Discovery

- `skaal.toml` is discovered by walking upward from the current working directory.
- `pyproject.toml` is discovered by walking upward from the current working directory until Skaal finds the nearest file.
- `.skaal.env` is loaded as an optional dotenv file from the working directory.
- Paths such as `out = "artifacts"` are interpreted relative to the current working directory.

## `skaal.toml`

This is the main environment file:

```toml
[env.local]
target = "local"

[env.prod]
target = "aws"
region = "us-east-1"

[env.prod.backends.aws]
table_prefix = "prod-"
lambda_defaults.memory = 1024
```

Supported keys on `[env.<name>]`:

| Key | Meaning |
| --- | --- |
| `target` | Required. One of `local`, `aws`, or `gcp`. |
| `region` | Optional region override for that environment. |
| `overrides` | Optional per-resource binding overrides. |
| `backends` | Optional per-backend configuration tables. |

Supported keys on `[env.<name>.backends.<backend>]` include:

- `region`
- `project`
- `dataset`
- `emulator`
- `table_prefix`
- any extra target-specific options under `options`

Example override block:

```toml
[env.prod.overrides]
"examples.todo_api.Todos" = "dynamodb"
```

## Full `pyproject.toml` Example

This example shows the CLI default surface that still lives in `[tool.skaal]`:

```toml
[tool.skaal]
app = "todo_api:app"
out = "artifacts"

stack = "dev"
gcp_project = "todo-dev"
overrides = { cloudRunMemory = "1Gi", cloudRunMinInstances = 1 }
deletion_protection = false
env = { APP_ENV = "development", FEATURE_SEARCH = "on" }
invokers = ["allUsers"]
labels = { service = "todo-api", owner = "platform" }
pre_deploy = [["skaal", "migrate", "relational", "upgrade"]]
post_deploy = [["python", "scripts/smoke_test.py"]]

[tool.skaal.logging]
level = "INFO"
format = "text"
loggers = { "skaal.deploy" = "INFO", "httpx" = "WARNING" }

[tool.skaal.stacks.dev]
region = "us-east-1"
env = { APP_ENV = "development" }
labels = { stage = "dev", service = "todo-api" }
pre_deploy = [["skaal", "migrate", "relational", "upgrade"]]

[tool.skaal.stacks.prod]
region = "europe-west1"
gcp_project = "todo-prod"
overrides = { cloudRunMemory = "2Gi", cloudRunMinInstances = 1 }
deletion_protection = true
env = { APP_ENV = "production" }
invokers = ["group:platform@example.com"]
labels = { stage = "prod", service = "todo-api" }
pre_deploy = [["skaal", "migrate", "relational", "upgrade"]]
post_deploy = [["python", "scripts/notify_deploy.py"]]
```

## `[tool.skaal]` Keys

| Key | Type | Used by | Meaning |
| --- | --- | --- | --- |
| `app` | string | `run`, `plan`, migration commands, Python API parity helpers | Default `MODULE:APP` when you omit it on the command line. |
| `out` | path | `build` | Default output directory for generated artifacts. |
| `stack` | string | `build`, `deploy`, `stacks` | Default stack profile or Pulumi stack name. |
| `gcp_project` | string | `deploy` | Default GCP project for GCP deploys. |
| `overrides` | table / dict | `deploy` | Raw Pulumi config overrides applied during deploy. |
| `deletion_protection` | bool | `deploy` | Shortcut that expands into Cloud SQL deletion-protection overrides. |
| `env` | table / dict | `deploy` | Literal environment variables baked into the compute container. |
| `invokers` | array of strings | `deploy` | IAM members allowed to invoke the service. |
| `labels` | table / dict | `deploy` | Labels applied to supporting resources. |
| `pre_deploy` | array of argv arrays | `deploy` | Commands run before `pulumi up`. |
| `post_deploy` | array of argv arrays | `deploy` | Commands run after a successful deploy. |
| `stacks` | table of stack profiles | `build`, `deploy`, `stacks` | Named per-stack overrides declared under `[tool.skaal.stacks.<name>]`. |

## `[tool.skaal.stacks.<name>]` Keys

Stack profiles can override the deploy-oriented fields above on a per-environment basis. These are the supported keys:

- `region`
- `gcp_project`
- `overrides`
- `deletion_protection`
- `env`
- `invokers`
- `labels`
- `pre_deploy`
- `post_deploy`

Profiles are applied as whole-field overrides, not deep merges. In practice that means:

- if a stack profile sets `labels`, that profile's `labels` value replaces the base one
- if a stack profile sets `pre_deploy`, it replaces the base list rather than appending to it

Keep full per-stack values in the profile when you need deterministic results.

## `[tool.skaal.logging]` Keys

CLI logging reads a separate nested section under `[tool.skaal.logging]`:

| Key | Type | Meaning |
| --- | --- | --- |
| `level` | string | Default root log level such as `WARNING`, `INFO`, or `DEBUG`. |
| `format` | `text` or `json` | Default CLI output format. |
| `loggers` | table / dict | Per-logger level overrides, for example `{ "skaal.deploy" = "INFO" }`. |

CLI flags still win over this section. For example, `skaal -vv plan ...` overrides `level = "WARNING"` from the config file.

## Environment Variables

### Shared settings env vars

These variables map onto the shared settings model.

| Variable | Maps to | Example |
| --- | --- | --- |
| `SKAAL_APP` | `tool.skaal.app` | `examples.counter:app` |
| `SKAAL_OUT` | `tool.skaal.out` | `artifacts` |
| `SKAAL_STACK` | `tool.skaal.stack` | `prod` |
| `SKAAL_GCP_PROJECT` | `tool.skaal.gcp_project` | `my-gcp-project` |
| `SKAAL_OVERRIDES` | `tool.skaal.overrides` | `{"cloudRunMemory":"2Gi","cloudRunMinInstances":1}` |
| `SKAAL_DELETION_PROTECTION` | `tool.skaal.deletion_protection` | `true` |
| `SKAAL_ENV` | reload auto-mode behavior | `development` |
| `SKAAL_INVOKERS` | `tool.skaal.invokers` | `["allUsers"]` |
| `SKAAL_LABELS` | `tool.skaal.labels` | `{"service":"todo-api","stage":"prod"}` |
| `SKAAL_PRE_DEPLOY` | `tool.skaal.pre_deploy` | `[["skaal","migrate","relational","upgrade"]]` |
| `SKAAL_POST_DEPLOY` | `tool.skaal.post_deploy` | `[["python","scripts/smoke_test.py"]]` |
| `SKAAL_STACKS` | `tool.skaal.stacks` | `{"prod":{"target":"gcp","region":"europe-west1"}}` |

For list and dict values, Skaal relies on `pydantic-settings`, so pass JSON strings in environment variables.

### Logging env vars

These affect CLI logging directly:

| Variable | Meaning |
| --- | --- |
| `SKAAL_LOG_FORMAT` | Override logging format with `text` or `json`. |
| `SKAAL_LOG_LEVEL` | Override the root log level with values such as `WARNING`, `INFO`, or `DEBUG`. |

### Generated hook env vars

During post-deploy hooks, Skaal exports Pulumi outputs as environment variables named `SKAAL_OUTPUT_<KEY>`. Those are generated by Skaal for hook commands; you do not normally set them yourself.

## `.skaal.env` Example

If you prefer keeping local defaults in a dotenv file instead of exporting them in your shell, create `.skaal.env` in the working directory:

```dotenv
SKAAL_APP=todo_api:app
SKAAL_STACK=dev
SKAAL_LOG_FORMAT=text
```

This is useful for machine-local defaults. For project-wide environment shape, prefer `skaal.toml`.

## Recommended Split

For most teams, this split stays readable:

- put named environments and backend options in `skaal.toml`
- put stable project defaults in `[tool.skaal]`
- put per-environment deploy behavior in `[tool.skaal.stacks.<name>]`
- use `.skaal.env` for local machine-only overrides
- use direct CLI flags for one-off command changes

## Related References

- Read [CLI](cli.md) for the command surface that consumes these settings.
- Read [Python API: CLI-Parity API](reference/python-api-cli-parity.md) if you want the in-process `skaal.api` equivalents.
