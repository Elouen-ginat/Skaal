# Configuring your environments

`[tool.skaal]` in `pyproject.toml` is now the main Skaal configuration surface.
It can define the default app target, the default environment and target, path
defaults, local runtime defaults, logging, backend defaults, and named
environments.

`skaal.toml` is still supported, but it is now the compatibility and
environment-catalog layer rather than the primary place to put project-level
defaults.

## Resolution Order

Skaal resolves config in this order:

1. explicit CLI flags or Python keyword arguments
2. `SKAAL_*` environment variables
3. `.skaal.env`
4. `[tool.skaal]` in the nearest `pyproject.toml`
5. `skaal.toml`
6. built-in defaults

That means `pyproject.toml` wins over `skaal.toml`, and env vars win over both.

Two related behaviors sit beside the structured settings model:

- `SKAAL_LOG_FORMAT` and `SKAAL_LOG_LEVEL` affect CLI logging.
- `SKAAL_ENV` still controls `skaal run` hot-reload auto mode. It is not the
	same thing as `SKAAL_DEFAULT_ENVIRONMENT`.

## File Discovery

- `pyproject.toml` is discovered by walking upward from the current working
	directory.
- `skaal.toml` is discovered the same way, unless `[tool.skaal].toml` or
	`[tool.skaal.paths].toml` points at a different file.
- `.skaal.env` is loaded from the current working directory when it exists.
- Relative paths such as `out = "artifacts"` or `lock = "custom.lock"` are
	interpreted relative to the current working directory.

## Recommended `pyproject.toml`

This is the preferred project-level shape:

```toml
[tool.skaal]
app = "examples.todo_api:app"
default_environment = "dev"
default_target = "local"
default_region = "eu-west-3"
toml = "skaal.toml"
lock = "skaal.lock"
out = "artifacts"

[tool.skaal.run]
host = "127.0.0.1"
port = 8000

[tool.skaal.logging]
level = "INFO"
format = "text"
loggers = { "skaal.deploy" = "DEBUG" }

[tool.skaal.backend_defaults.gcp]
project = "acme-prod"

[tool.skaal.backend_defaults.dynamodb]
table_prefix = "acme-"

[tool.skaal.environments.dev]
region = "eu-west-1"

[tool.skaal.environments.prod]
target = "aws"
region = "eu-west-3"

[tool.skaal.environments.prod.overrides]
"examples.todo_api:Todos" = "dynamodb"
"examples.todo_api:Assets" = { backend = "s3", region = "us-east-1" }

[tool.skaal.environments.prod.backends.bigquery]
dataset = "warehouse"
```

With that in place, the everyday loop gets shorter:

```bash
skaal plan
skaal build
skaal run
skaal deploy --preview
```

The positional `module:attribute` target and `--env` flag become optional when
the configured defaults are enough.

## `[tool.skaal]` Keys

| Key | Type | Meaning |
| --- | --- | --- |
| `app` | string | Default `module:attribute` target for CLI commands when you omit it. |
| `default_environment` | string | Default environment name used when `--env` is omitted. |
| `default_target` | `local` / `aws` / `gcp` | Default target used when an environment omits `target`, or when Skaal synthesizes a baseline environment. |
| `default_region` | string | Default region applied when an environment omits `region`. |
| `toml` | path | Override the discovered `skaal.toml` path. |
| `lock` | path | Default `skaal.lock` path. |
| `out` | path | Base output directory for `skaal build`, `skaal deploy`, and `skaal destroy`. Skaal appends `/<env>` by default. |
| `run` | table | Local runtime defaults such as `host` and `port`. |
| `logging` | table | CLI logging defaults. |
| `backend_defaults` | table of backend configs | Per-backend defaults merged into every environment unless the environment overrides them. |
| `environments` | table of named environments | Named environment definitions keyed by environment name. |

## `[tool.skaal.run]`

| Key | Type | Meaning |
| --- | --- | --- |
| `host` | string | Default host for `skaal run`. |
| `port` | integer | Default port for `skaal run`. |

## `[tool.skaal.logging]`

| Key | Type | Meaning |
| --- | --- | --- |
| `level` | string | Default root log level such as `WARNING`, `INFO`, or `DEBUG`. |
| `format` | `text` or `json` | Default CLI logging format. |
| `loggers` | table | Per-logger level overrides, for example `{ "skaal.deploy" = "INFO" }`. |

## Environment Shape

Named environments live under `[tool.skaal.environments.<name>]` in
`pyproject.toml`, or under `[env.<name>]` in `skaal.toml`.

Supported keys on one environment:

| Key | Meaning |
| --- | --- |
| `target` | Optional. When omitted, inherits `default_target` or `[defaults].target`. |
| `region` | Optional. When omitted, inherits `default_region` or `[defaults].region`. |
| `overrides` | Optional per-resource backend overrides. String shorthand is accepted. |
| `backends` | Optional per-backend configuration tables. |

Supported backend config keys:

- `region`
- `project`
- `dataset`
- `emulator`
- `table_prefix`
- any extra backend-specific keys, which Skaal preserves under `options`

## `skaal.toml` Compatibility

`skaal.toml` can still carry the same information, especially for teams that
prefer a separate environment catalog.

```toml
[defaults]
target = "aws"
region = "eu-west-1"

[backend_defaults.dynamodb]
table_prefix = "acme-"

[env.dev]
region = "eu-west-1"

[env.prod]
region = "eu-west-3"

[env.prod.overrides]
"examples.todo_api:Todos" = "dynamodb"

[env.prod.backends.gcp]
project = "acme-prod"
dataset = "warehouse"
```

`pyproject.toml` still wins when both files define the same field.

## Environment Variables

The structured model supports both simple flat env vars and nested `__`
notation.

### Common flat env vars

| Variable | Meaning |
| --- | --- |
| `SKAAL_APP` | Default `module:attribute` app target. |
| `SKAAL_DEFAULT_ENVIRONMENT` | Default environment name used when `--env` is omitted. |
| `SKAAL_DEFAULT_TARGET` | Default target for synthesized or partially-defined environments. |
| `SKAAL_DEFAULT_REGION` | Default region fallback. |
| `SKAAL_TOML` | Override the discovered `skaal.toml` path. |
| `SKAAL_LOCK` | Override the default lock-file path. |
| `SKAAL_OUT` | Override the base build-output directory. |
| `SKAAL_RUN_HOST` | Default host for `skaal run`. |
| `SKAAL_RUN_PORT` | Default port for `skaal run`. |
| `SKAAL_LOG_LEVEL` | Override the root log level. |
| `SKAAL_LOG_FORMAT` | Override the log format with `text` or `json`. |
| `SKAAL_LOG_LOGGERS` | JSON object of per-logger overrides. |
| `SKAAL_ENVIRONMENTS` | JSON object containing named environments. |
| `SKAAL_BACKEND_DEFAULTS` | JSON object containing backend defaults. |

### Nested env vars

Nested objects can be expressed with `__` separators. For example:

```dotenv
SKAAL_ENVIRONMENTS__prod__target=aws
SKAAL_ENVIRONMENTS__prod__region=eu-west-3
SKAAL_ENVIRONMENTS__prod__backends__gcp__project=acme-prod
```

For dict and list payloads in flat variables, pass JSON strings.

## `.skaal.env` Example

If you prefer local machine defaults in a dotenv file:

```dotenv
SKAAL_APP=examples.todo_api:app
SKAAL_DEFAULT_ENVIRONMENT=dev
SKAAL_OUT=artifacts
SKAAL_LOG_FORMAT=text
```

Use `.skaal.env` for machine-local overrides. Use `pyproject.toml` for shared
project defaults.

## Recommended Split

- Put stable project defaults in `[tool.skaal]` inside `pyproject.toml`.
- Put named environments in `[tool.skaal.environments]` unless your team prefers
	a separate `skaal.toml` catalog.
- Use `backend_defaults` for shared backend config such as table prefixes or a
	GCP project id.
- Use `.skaal.env` for developer-machine overrides.
- Use direct CLI flags for one-off commands.

## Related References

- Read [CLI](cli.md) for the commands that consume these settings.
- Read [Python API: CLI-Parity API](reference/python-api-cli-parity.md) if you
	want the in-process `skaal.api` equivalents.
