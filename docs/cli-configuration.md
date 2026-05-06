# CLI Configuration

Skaal's CLI configuration is intentionally simple: the commands read one shared settings model, and every command fills in missing arguments from that model only when you did not pass a flag explicitly.

## Resolution Order

For the shared CLI settings, Skaal resolves values in this order:

1. explicit CLI flags or Python keyword arguments
2. `SKAAL_*` environment variables
3. `.skaal.env`
4. `[tool.skaal]` in the nearest `pyproject.toml`
5. built-in defaults

Two related behaviors sit beside that main settings model:

- `SKAAL_LOG_FORMAT` and `SKAAL_LOG_LEVEL` affect CLI logging.
- `SKAAL_ENV` affects `skaal run` hot-reload auto mode and is treated as a runtime behavior flag rather than a normal structured setting.

## File Discovery

- `pyproject.toml` is discovered by walking upward from the current working directory until Skaal finds the nearest file.
- `.skaal.env` is loaded as an optional dotenv file from the working directory.
- Paths such as `catalog = "catalogs/local.toml"` or `out = "artifacts"` are interpreted relative to the current working directory.

## Full `pyproject.toml` Example

This example shows the full configuration surface that Skaal's shared settings and CLI logging consume:

```toml
[tool.skaal]
app = "todo_api:app"
target = "local"
region = "us-east-1"
out = "artifacts"
catalog = "catalogs/local.toml"
enable_mesh = false

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
target = "local"
region = "us-east-1"
catalog = "catalogs/local.toml"
env = { APP_ENV = "development" }
labels = { stage = "dev", service = "todo-api" }
pre_deploy = [["skaal", "migrate", "relational", "upgrade"]]

[tool.skaal.stacks.prod]
target = "gcp"
region = "europe-west1"
catalog = "catalogs/gcp.toml"
gcp_project = "todo-prod"
enable_mesh = false
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
| `target` | string | `plan`, stack profile resolution, Python API parity helpers | Default target when you do not pass `--target`. Common values are `local`, `aws`, and `gcp`. |
| `region` | string | `build`, `deploy` | Default region for generated artifacts and deploys. |
| `out` | path | `build` | Default output directory for generated artifacts. |
| `catalog` | path | `plan` and any code path that resolves catalogs implicitly | Default catalog path. |
| `enable_mesh` | bool | artifact generation | Include the mesh runtime dependency in generated artifacts. |
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

- `target`
- `region`
- `catalog`
- `gcp_project`
- `enable_mesh`
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
| `SKAAL_TARGET` | `tool.skaal.target` | `local` |
| `SKAAL_REGION` | `tool.skaal.region` | `us-east-1` |
| `SKAAL_OUT` | `tool.skaal.out` | `artifacts` |
| `SKAAL_CATALOG` | `tool.skaal.catalog` | `catalogs/aws.toml` |
| `SKAAL_ENABLE_MESH` | `tool.skaal.enable_mesh` | `true` |
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
SKAAL_TARGET=local
SKAAL_REGION=us-east-1
SKAAL_CATALOG=catalogs/local.toml
SKAAL_STACK=dev
SKAAL_LOG_FORMAT=text
```

This is useful for local development, but for project defaults that should travel with the repo, `pyproject.toml` is usually the better home.

## Recommended Split

For most teams, this split stays readable:

- put stable project defaults in `[tool.skaal]`
- put per-environment deploy behavior in `[tool.skaal.stacks.<name>]`
- use `.skaal.env` for local machine-only overrides
- use direct CLI flags for one-off command changes

## Related References

- Read [CLI](cli.md) for the command surface that consumes these settings.
- Read [Python API: CLI-Parity API](reference/python-api-cli-parity.md) if you want the in-process `skaal.api` equivalents.
