# Global development guidelines for the Skaal project

This document provides context to understand the Skaal Python project and assist with development.

## Project architecture and context

### Project overview

**Skaal** is an "Infrastructure as Constraints" Python framework. Developers declare resource constraints (latency, durability, throughput, access patterns) via decorators, and a Z3 SMT solver selects the cheapest backend that satisfies all constraints from a TOML catalog. The framework then generates deployment artifacts for local, AWS, GCP, or Kubernetes targets.

- **License:** GPL-3.0-or-later
- **Python:** >=3.11 (tested on 3.11, 3.12, 3.13)
- **Status:** Alpha (0.3.1)

### Repository structure

```txt
skaal/
├── skaal/                  # Main Python package
│   ├── __init__.py         # Public API exports
│   ├── app.py              # `App` class (extends `Module`)
│   ├── module.py           # Core `Module` (composable units)
│   ├── agent.py            # Virtual actor base class
│   ├── api.py              # Python API (equivalents to CLI verbs)
│   ├── storage.py          # `Map[K, V]`, `Collection[T]` typed containers
│   ├── decorators.py       # `@storage`, `@compute`, `@scale`, `@handler`, `@shared`
│   ├── components.py       # `APIGateway`, `ExternalStorage`, `Proxy`, etc.
│   ├── patterns.py         # `EventLog`, `Outbox`, `Projection`, `Saga`
│   ├── channel.py          # Cross-process messaging
│   ├── schedule.py         # `Cron`, `Every` scheduling primitives
│   ├── settings.py         # Unified config (env vars + pyproject.toml)
│   ├── plan.py             # `PlanFile` output structure
│   ├── types/              # Constraint types (`Latency`, `Durability`, `AccessPattern`, …)
│   ├── backends/           # Storage backend implementations (sqlite, redis, postgres, firestore, dynamodb, …)
│   ├── solver/             # Z3 constraint solver (storage, compute, components, graph, targets)
│   ├── runtime/            # Local execution engine (uvicorn + asyncio)
│   ├── deploy/             # Code generation for cloud targets (AWS, GCP, local)
│   │   └── templates/      # Jinja2 templates (Dockerfile, handler entrypoints, Pulumi programs)
│   ├── cli/                # CLI commands (typer)
│   ├── catalog/            # TOML catalog loading & models
│   └── migrate/            # Schema migration engine (6-stage)
├── mesh/                   # Rust PyO3 module (Phase 4+ stubs for agent routing, state sync)
├── tests/                  # Pytest test suite (mirrors `skaal/` layout)
├── catalogs/               # Infrastructure catalogs (`local.toml`, `aws.toml`, `gcp.toml`)
├── examples/               # Reference apps (counter, hello_world, todo_api, dash_app, …)
├── docs/                   # MkDocs site sources
│   └── design/             # Architecture Decision Records (ADR 001-007)
├── .github/                # CI/CD workflows and templates
└── README.md               # Project entry point
```

- **Constraint layer** (`skaal.types`, `skaal.decorators`): user-facing primitives for declaring infrastructure requirements.
- **Solver layer** (`skaal.solver`): Z3 SMT pipeline that maps constraints to concrete backends from a catalog.
- **Backend layer** (`skaal.backends`): concrete implementations of storage and channel abstractions.
- **Deploy layer** (`skaal.deploy`): Jinja2-driven code generation for Pulumi programs, Dockerfiles, and handler entrypoints.
- **Runtime layer** (`skaal.runtime`): local execution engine built on Starlette + Uvicorn.

### Development tools & commands

- `uv` – Fast Python package installer and resolver (replaces pip/poetry)
- `make` – Task runner for common development commands. See the `Makefile` for the full list.
- `ruff` – Fast Python linter and formatter
- `mypy` – Static type checking
- `pytest` – Testing framework
- `maturin` – Build backend for the Rust `mesh/` PyO3 extension

This repository uses `uv` for dependency management with `[dependency-groups]` defined in `pyproject.toml`.

Before running tests, install the appropriate dependency groups:

```bash
# Editable install with all dev tooling
pip install -e ".[dev]"

# Or, with uv
uv sync --group dev

# Install only the test group
uv sync --group test
```

#### Common commands

```bash
# Quality
make lint                        # ruff check skaal tests examples
make format                      # ruff format skaal tests examples
make typecheck                   # mypy skaal

# Testing
make test                        # pytest tests/ -q
make test-cov                    # pytest with coverage
make test-solver                 # solver tests only
make test-storage                # storage tests only
make test-runtime                # runtime tests only
make test-schema                 # schema migration tests only

# Single test file
uv run --group test pytest tests/path/to/test_file.py

# Rust extension
make build                       # maturin build --release
make build-dev                   # maturin develop
```

#### Key config files

- `pyproject.toml`: project metadata, dependencies, dependency groups, and tool configuration (ruff, mypy, pytest, coverage, bandit, hatch, skaal defaults).
- `uv.lock`: locked dependencies for reproducible builds.
- `Makefile`: development task entry points.
- `.pre-commit-config.yaml`: hooks executed on every commit.
- `catalogs/*.toml`: infrastructure catalogs consumed by the solver.

#### PR and commit titles

Follow Conventional Commits. Keep titles short and descriptive — save detail for the body.

- Start the text after `type(scope):` with a lowercase letter, unless the first word is a proper noun (e.g. `AWS`, `GCP`, `Z3`) or a named entity (class, function, method, parameter, or variable name).
- Wrap named entities in backticks so they render as code. Proper nouns are left unadorned.
- Suggested scopes mirror the top-level subsystems: `solver`, `runtime`, `deploy`, `backends`, `cli`, `catalog`, `migrate`, `types`, `docs`, `ci`, `mesh`.

Examples:

```txt
feat(solver): add throughput dimension to compute fitting
fix(backends): handle reconnection in `RedisBackend`
chore(ci): pin GitHub Actions to commit SHAs
docs(design): add ADR-008 for vector backend selection
feat(cli): `skaal doctor` checks pulumi availability
```

#### PR descriptions

The description *is* the summary — do not add a `# Summary` header.

- When the PR closes an issue, lead with the closing keyword on its own line at the very top, followed by a horizontal rule and then the body:

  ```txt
  Closes #123

  ---

  <rest of description>
  ```

  Only `Closes`, `Fixes`, and `Resolves` auto-close the referenced issue on merge. `Related:` or similar labels are informational and do not close anything.

- Explain the *why*: the motivation and why this solution is the right one. Limit prose.
- Write for readers who may be unfamiliar with this area of the codebase. Avoid insider shorthand.
- Do **not** cite line numbers; they go stale as soon as the file changes.
- Rarely include full file paths or filenames. Reference the affected symbol, class, or subsystem by name instead.
- Wrap class, function, method, parameter, and variable names in backticks.
- Skip dedicated "Test plan" or "Testing" sections in most cases. Mention tests only when coverage is non-obvious, risky, or otherwise notable.
- Call out areas of the change that require careful review (e.g. solver semantics, generated artifact changes, migration ordering).
- Add a brief disclaimer noting AI-agent involvement in the contribution.

## Core development principles

### Maintain stable public interfaces

CRITICAL: Always attempt to preserve function signatures, argument positions, and names for exported/public methods. Do not make breaking changes silently.
You should warn the developer for any function signature changes, regardless of whether they look breaking or not.

**Before making ANY changes to public APIs:**

- Check whether the symbol is exported in `skaal/__init__.py` (the `__all__` list is authoritative).
- Look for existing usage patterns in `tests/`, `examples/`, and `docs/`.
- Use keyword-only arguments for new parameters: `*, new_param: str = "default"`.
- Mark experimental features clearly with docstring warnings (using MkDocs Material admonitions, like `!!! warning`).
- Constraint types in `skaal.types` and decorators in `skaal.decorators` are the most user-facing API surface — treat them as load-bearing.

Ask: "Would this change break someone's code or break an existing `PlanFile` if they used it last week?"

### Code quality standards

All Python code MUST include type hints and return types. The `skaal.types.*` and `skaal.solver.*` modules are subject to stricter `mypy` checks (`disallow_untyped_defs`, `warn_return_any`) per `pyproject.toml`.

```python title="Example"
def filter_unknown_backends(backends: list[str], known: set[str]) -> list[str]:
    """Single line description of the function.

    Any additional context about the function can go here.

    Args:
        backends: List of backend identifiers to filter.
        known: Set of registered backend identifiers.

    Returns:
        List of backends that are not in the `known` set.
    """
```

- Use descriptive, self-explanatory variable names.
- Follow existing patterns in the codebase you're modifying.
- Prefer breaking up complex functions (>20 lines) into smaller, focused functions when it improves readability.
- Async-first: prefer async functions for all I/O operations (`aiosqlite`, `asyncpg`, `redis.asyncio`, `httpx`).

### Testing requirements

Every new feature or bugfix MUST be covered by tests.

- Unit tests live under `tests/` in subdirectories that mirror `skaal/`.
- Integration tests are marked with `@pytest.mark.integration`. AWS/GCP-specific suites use the `aws` / `gcp` markers.
- The framework is `pytest` with `pytest-asyncio` in `asyncio_mode = "auto"` — async tests do not need an explicit marker.
- HTTP calls are mocked via `pytest-httpx`.
- An autouse fixture in `tests/conftest.py` resets the migration registry between tests.
- Coverage gate is `fail_under = 60` (see `[tool.coverage.report]`).

**Checklist:**

- [ ] Tests fail when your new logic is broken
- [ ] Happy path is covered
- [ ] Edge cases and error conditions are tested
- [ ] Use fixtures/mocks for external dependencies (Redis, Postgres, S3, GCS)
- [ ] Tests are deterministic (no flaky tests)
- [ ] Solver changes include a test asserting on the resulting `PlanFile`
- [ ] Backend changes are exercised through the contract suite in `tests/storage/`

### Security and risk assessment

Bandit runs in pre-commit at medium severity (`tests/`, `examples/`, and `skaal/deploy/templates/` are excluded).

- No `eval()`, `exec()`, or `pickle` on user-controlled input — catalogs and plan files are loaded with TOML/JSON, never `pickle`.
- Proper exception handling (no bare `except:`); use a `msg` variable when raising and let the CLI's Rich formatter render it.
- Remove unreachable/commented code before committing.
- Watch for race conditions or resource leaks in async code (file handles, sockets, connection pools, scheduler tasks).
- Ensure proper async cleanup — prefer `async with` for backends that own connections.
- Generated deployment artifacts (Pulumi programs, Dockerfiles) must not embed secrets — they should reference environment variables or the configured secrets backend.

### Documentation standards

Use Google-style docstrings with an `Args` section for all public functions.

```python title="Example"
def select_backend(constraints: Constraints, *, target: str = "local") -> Backend:
    """Select the cheapest backend that satisfies all constraints.

    Any additional context about the function can go here.

    Args:
        constraints: The constraint bundle attached to a storage or compute resource.
        target: Deployment target name (`local`, `aws`, `gcp`).

    Returns:
        A `Backend` instance from the active catalog.

    Raises:
        UnsatisfiableConstraintsError: If no catalog entry can satisfy the constraints.
        CatalogNotLoadedError: If the catalog has not been loaded yet.
    """
```

- Types go in function signatures, NOT in docstrings.
  - If a default is present, DO NOT repeat it in the docstring unless there is post-processing or it is set conditionally.
- Focus on "why" rather than "what" in descriptions.
- Document all parameters, return values, and exceptions.
- Keep descriptions concise but clear.
- Ensure American English spelling (e.g., "behavior", not "behaviour").
- Do NOT use Sphinx-style double backtick formatting (` ``code`` `). Use single backticks (`` `code` ``) for inline code references in docstrings and comments.
- ADRs go under `docs/design/` as numbered Markdown files. Reference them from PR descriptions when changing solver semantics or generated artifact structure.

## Architecture and key patterns

### Constraint declaration

Decorators (`@app.storage`, `@app.compute`, `@app.scale`, `@app.handler`, `@app.shared`) attach metadata to classes and callables. Metadata is stored in `__skaal_storage__`, `__skaal_compute__`, etc. dunder attributes — never read these directly from user code.

### Solver pipeline

1. The user's `App` declares constraints via decorators.
2. `skaal plan` loads a TOML catalog and feeds constraints to the Z3 solver.
3. The solver outputs a `PlanFile` (JSON) mapping each resource to a concrete backend.
4. `skaal build` generates deployment artifacts from the plan using Jinja2 templates.
5. `skaal deploy` provisions infrastructure via Pulumi.

### Storage abstractions

- `Map[K, V]` — key-value store
- `Collection[T]` — document collection
- Backends are registered via the `skaal.backends` entry-point group in `pyproject.toml`. Built-ins: `local`, `sqlite`, `local-blob`, `redis`, `postgres`, `chroma`, `pgvector`, `dynamodb`, `firestore`, `s3`, `gcs`.

### Channels

- Cross-process messaging via `skaal.channel`.
- Channel backends are registered via the `skaal.channels` entry-point group. Built-ins: `local`, `redis`.

### Modules

- `Module` is the composable unit; `App` extends `Module`.
- Modules can include other modules via `app.include(module)`.

## Code conventions

- **Naming:** PascalCase for classes, snake_case for functions/variables.
- **Type hints:** used throughout; leverages `TypeVar` and generics. Stricter rules apply in `skaal.types.*` and `skaal.solver.*`.
- **Async-first:** prefer async functions for all I/O operations.
- **Imports:** organized by isort (enforced by Ruff `I` rule). First-party packages: `skaal`, `mesh`.
- **Public API:** all public symbols are exported from `skaal/__init__.py` with explicit `__all__`.
- **Error handling:** standard Python exceptions; CLI wraps errors with Rich formatting.
- **TOML catalogs:** infrastructure backends are declared in `catalogs/*.toml`, not in code.
- **Settings:** `[tool.skaal]` in `pyproject.toml` or `SKAAL_*` environment variables; CLI flags take precedence.

### Linting and formatting

**Ruff** is the primary linter and formatter:

- Line length: 100 (E501 is ignored — long lines allowed).
- Active rule sets: `E`, `F`, `I`, `B`, `UP`, `SIM`, `C4`, `RUF`, `ASYNC`, `PTH`, `PIE`, `PERF`, `TID`.
- Target: Python 3.11.
- Per-file ignores relax `B/SIM/PERF/PTH` for `tests/` and `examples/`; `skaal/cli/templates/**` is fully excluded.

**MyPy** for type checking:

- `strict = false`, `ignore_missing_imports = true`, `check_untyped_defs = true`.
- Uses the `pydantic.mypy` plugin.
- Excludes `tests/`, `examples/`, and `skaal/deploy/templates/`.
- Stricter overrides for `skaal.types.*` and `skaal.solver.*`.

**Pre-commit hooks** run automatically on `git commit`:

- Ruff (lint + format with auto-fix)
- MyPy (type checking, excludes tests/examples/templates)
- Bandit (security scanning, medium severity)
- Yamllint (120 char max)
- Trailing whitespace, end-of-file fixer, check-yaml/json/toml, debug-statements, mixed-line-ending (LF)

The `skaal/deploy/templates/` directory is excluded from most hooks since it contains Jinja2 templates, not valid Python/YAML.

## CI/CD infrastructure

GitHub Actions workflows live in `.github/workflows/`:

- `ci.yml` — pre-commit job (Python 3.11) and pytest matrix (Python 3.11, 3.12, 3.13). Dependencies installed via `uv sync --group dev`.
- `release.yml` — triggered by `v*` tags, builds and publishes to PyPI.
- `docs.yml` — builds and deploys the MkDocs site.

### GitHub Actions pinning

Actions should be pinned to a full-length commit SHA where possible. Verify tags are not annotated tag objects (which would need dereferencing). Use the `gh` CLI to query.

### Adding a new backend

When introducing a new storage or channel backend:

- Add the implementation under `skaal/backends/` (or the appropriate subpackage).
- Register the entry point in `pyproject.toml` under `[project.entry-points."skaal.backends"]` or `"skaal.channels"`.
- Add a catalog entry to the relevant `catalogs/*.toml` so the solver can select it.
- Add a contract test under `tests/storage/` or `tests/backends/`.
- Document the backend's constraint coverage in `docs/catalogs.md`.

## Key dependencies

| Package | Purpose |
|---------|---------|
| `z3-solver` | Constraint solving (SMT solver) |
| `pydantic` / `pydantic-settings` | Validation and settings |
| `sqlmodel` / `alembic` | ORM and schema migrations |
| `typer` | CLI framework |
| `rich` | Terminal output formatting |
| `starlette` / `uvicorn` | Local web runtime (extra: `serve`) |
| `redis` | Redis backend |
| `aiosqlite` | SQLite async backend |
| `httpx` | HTTP client |
| `apscheduler` | Scheduling |
| `tenacity` / `pybreaker` | Retries and circuit breakers |
| `langgraph` | Agent orchestration |
| `fsspec` | Filesystem abstractions |
| `maturin` | Rust/PyO3 extension build |

Optional extras: `aws` (`boto3`, `pulumi-aws`, `asyncpg`, `s3fs`); `gcp` (`google-cloud-*`, `pulumi-gcp`, `gcsfs`); `vector` (`langchain-*`, `chromadb`, `psycopg`); `fastapi`, `dash`, `mesh`, `secrets-aws`, `secrets-gcp`.

## Working with this repo

- Always run `make lint` and `make test` before committing.
- Pre-commit hooks auto-fix formatting; if a commit is rejected, check the staged changes and retry.
- The `skaal/deploy/templates/` directory contains Jinja2 templates (not valid Python) — exclude from linting.
- Design decisions are documented in `docs/design/` as numbered ADRs.
- The Rust `mesh/` crate is Phase 4 stub code — it compiles but contains placeholder implementations.
- Settings can be configured via `[tool.skaal]` in `pyproject.toml` or `SKAAL_*` environment variables.

## Additional resources

- **Documentation:** built with MkDocs Material; sources in `docs/`. Run `mkdocs serve` after `uv sync --group docs`.
- **Contributing Guide:** [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Citation:** see [`CITATION.cff`](CITATION.cff).
- **Issues:** https://github.com/Elouen-ginat/Skaal/issues
