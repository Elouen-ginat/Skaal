# CLAUDE.md

This file provides guidance for AI assistants working on the Skaal codebase.

## Project Overview

**Skaal** is an "Infrastructure as Constraints" Python framework. Developers declare resource constraints (latency, durability, throughput) via decorators, and a Z3 SMT solver selects the cheapest backend that satisfies all constraints from a TOML catalog. The framework then generates deployment artifacts for local, AWS, GCP, or Kubernetes targets.

- **License:** GPL-3.0-or-later
- **Python:** >=3.11 (tested on 3.11, 3.12, 3.13)
- **Status:** Alpha (0.1.0)

## Repository Structure

```
skaal/                  # Main Python package
  __init__.py           # Public API exports
  app.py                # App class (extends Module)
  module.py             # Core Module (composable units)
  agent.py              # Virtual actor base class
  api.py                # Python API (equivalents to CLI verbs)
  storage.py            # Map[K,V], Collection[T] typed containers
  decorators.py         # @storage, @compute, @scale, @handler, @shared
  components.py         # APIGateway, ExternalStorage, Proxy, etc.
  patterns.py           # EventLog, Outbox, Projection, Saga
  channel.py            # Cross-process messaging
  schedule.py           # Cron, Every scheduling primitives
  settings.py           # Unified config (env vars + pyproject.toml)
  plan.py               # PlanFile output structure
  types/                # Constraint types (Latency, Durability, AccessPattern, etc.)
  backends/             # Storage backend implementations (sqlite, redis, postgres, firestore, dynamodb)
  solver/               # Z3 constraint solver (storage, compute, components, graph, targets)
  runtime/              # Local execution engine (uvicorn + asyncio)
  deploy/               # Code generation for cloud targets (AWS, GCP, local)
    templates/          # Jinja2 templates (Dockerfile, handler entrypoints, Pulumi programs)
  cli/                  # CLI commands (typer)
  catalog/              # TOML catalog loading & models
  migrate/              # Schema migration engine (6-stage)
mesh/                   # Rust PyO3 module (Phase 4+ stubs for agent routing, state sync)
tests/                  # Pytest test suite
  solver/               # Z3 solver tests
  storage/              # Backend contract & storage tests
  runtime/              # Local runtime tests
  deploy/               # Code generation tests
  agent/                # Agent lifecycle tests
  api/                  # Python API tests
  backends/             # Backend implementation tests
  schema/               # Schema migration tests
  cli/                  # CLI command tests
catalogs/               # Infrastructure catalogs (local.toml, aws.toml, gcp.toml)
examples/               # Reference apps (counter, hello_world, todo_api, dash_app)
docs/design/            # Architecture Decision Records (ADR 001-007)
```

## Quick Reference Commands

```bash
# Setup
pip install -e ".[dev]"          # or: uv sync --group dev
pre-commit install               # install git hooks

# Quality
make lint                        # ruff check skaal tests examples
make format                      # ruff format skaal tests examples
make typecheck                   # mypy skaal

# Testing
make test                        # pytest tests/ -q
make test-cov                    # pytest with coverage
make test-solver                 # just solver tests
make test-storage                # just storage tests
make test-runtime                # just runtime tests
make test-schema                 # just schema tests
pytest tests/path/to/test.py    # single test file

# Build (Rust extension)
make build                       # maturin build --release
make build-dev                   # maturin develop
```

## Testing

- **Framework:** pytest with pytest-asyncio (asyncio_mode = "auto")
- **Test paths:** all under `tests/` in subdirectories mirroring the source structure
- **Fixtures:** `tests/conftest.py` has an autouse fixture that resets the migration registry between tests
- Additional fixtures in `tests/storage/conftest.py`, `tests/solver/conftest.py`, `tests/runtime/conftest.py`, `tests/schema/conftest.py`
- Tests use `pytest-httpx` for HTTP mocking
- All async test functions are auto-detected (no need for `@pytest.mark.asyncio`)

## Linting and Formatting

**Ruff** is the primary linter and formatter:
- Line length: 100 (E501 is ignored — long lines allowed)
- Rules: E (pycodestyle errors), F (pyflakes), I (isort)
- Target: Python 3.11

**MyPy** for type checking:
- strict = false, ignore_missing_imports = true
- Uses pydantic.mypy plugin
- Excludes tests/, examples/, and deploy/templates/

**Pre-commit hooks** run automatically on `git commit`:
- Ruff (lint + format with auto-fix)
- MyPy (type checking, excludes tests/examples/templates)
- Bandit (security scanning, medium severity, excludes tests/templates)
- Yamllint (120 char max)
- Trailing whitespace, end-of-file fixer, check-yaml/json/toml, debug-statements, mixed-line-ending (LF)

The `skaal/deploy/templates/` directory is excluded from most hooks since it contains Jinja2 templates, not valid Python/YAML.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`):
1. **Pre-commit job:** runs all hooks on ubuntu-latest with Python 3.11
2. **Test matrix:** runs pytest on Python 3.11, 3.12, 3.13

Release pipeline (`.github/workflows/release.yml`): triggered by `v*` tags, builds and publishes to PyPI.

Dependencies are installed via `uv sync --group dev` in CI.

## Architecture and Key Patterns

### Constraint Declaration
Decorators (`@app.storage`, `@app.compute`, `@app.scale`) attach metadata to classes. Metadata is stored in `__skaal_storage__`, `__skaal_compute__`, etc. dunder attributes.

### Solver Pipeline
1. App declares constraints via decorators
2. `skaal plan` loads a TOML catalog and feeds constraints to the Z3 solver
3. Solver outputs a `PlanFile` (JSON) mapping each resource to a concrete backend
4. `skaal build` generates deployment artifacts from the plan using Jinja2 templates
5. `skaal deploy` provisions infrastructure via Pulumi

### Storage Abstractions
- `Map[K, V]` — key-value store
- `Collection[T]` — document collection
- Backends: LocalMap (in-memory), SQLite, Redis, Postgres, Firestore, DynamoDB

### Runtime
- Local runtime uses Starlette + Uvicorn
- Async-first: all I/O is async (`aiosqlite`, `asyncpg`, `redis.asyncio`)
- Agents (virtual actors) have persistent identity managed by `AgentRegistry`

### Modules
- `Module` is the composable unit; `App` extends `Module`
- Modules can include other modules via `app.include(module)`

## Code Conventions

- **Naming:** PascalCase for classes, snake_case for functions/variables
- **Type hints:** used throughout; leverages TypeVar and generics
- **Async-first:** prefer async functions for all I/O operations
- **Imports:** organized by isort (enforced by Ruff `I` rule)
- **Public API:** all public symbols are exported from `skaal/__init__.py` with explicit `__all__`
- **Error handling:** standard Python exceptions; CLI wraps errors with Rich formatting
- **TOML catalogs:** infrastructure backends are declared in `catalogs/*.toml`, not in code

## Key Dependencies

| Package | Purpose |
|---------|---------|
| z3-solver | Constraint solving (SMT solver) |
| pydantic / pydantic-settings | Validation and settings |
| typer | CLI framework |
| rich | Terminal output formatting |
| starlette / uvicorn | Local web runtime |
| redis | Redis backend |
| aiosqlite | SQLite async backend |
| httpx | HTTP client |
| apscheduler | Scheduling |
| maturin | Rust/PyO3 extension build |

Optional: `boto3`, `pulumi`, `pulumi-aws` (AWS extra); `google-cloud-*`, `pulumi-gcp` (GCP extra).

## Working with This Repo

- Always run `make lint` and `make test` before committing
- Pre-commit hooks auto-fix formatting; if a commit is rejected, check the staged changes and retry
- The `skaal/deploy/templates/` directory contains Jinja2 templates (not valid Python) — exclude from linting
- Design decisions are documented in `docs/design/` as numbered ADRs
- The Rust `mesh/` crate is Phase 4 stub code — it compiles but contains placeholder implementations
- Settings can be configured via `[tool.skaal]` in `pyproject.toml` or `SKAAL_*` environment variables
