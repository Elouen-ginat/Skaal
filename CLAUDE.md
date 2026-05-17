# Global development guidelines for the Skaal project

This document provides context to understand the Skaal Python project and assist with development.

> **Redesign in progress.** Skaal is moving from "Infrastructure as Constraints" (the `0.3.x` line) to "code-first infrastructure" per [ADR 028](notes/design/028-code-first-infra-redesign.md). The execution plan is [ADR 029](notes/design/029-redesign-foundation-implementation-plan.md); live progress is in [`notes/redesign-status.md`](notes/redesign-status.md). The constraint vocabulary (`Latency`, `Durability`, `AccessPattern`, `@app.handler`, `@app.scale`, `@app.shared`, TOML catalogs, the Z3 solver) is being removed root and branch — no backwards-compatibility shims. This file's "Architecture and key patterns" section will be rewritten in full once the redesign reaches Phase 7; until then, treat the architecture descriptions below as historical until each phase exits.

## Project architecture and context

### Project overview

**Skaal** is a Python framework where the application code is the infrastructure declaration. Developers write classes (`Store[T]`, `BlobStore`, `Channel[T]`, `Relational[T, B]`) and functions (`@app.function`, `@app.schedule`, `@app.job`); Skaal infers the architecture, generates Pulumi programs, and provides typed clients for every primitive. Targets: local, AWS, and GCP.

- **License:** GPL-3.0-or-later
- **Python:** >=3.11 (tested on 3.11, 3.12, 3.13)
- **Status:** Alpha (`0.4.0a0`); redesign per ADR 028 in flight on the `claude/plan-redesign-strategy-A5ixu` working branch (the de-facto `v0.4.0-alpha`)

### Repository structure

Entries marked **(deletion pending — Phase 1)** are scheduled for removal per ADR 029 and still exist on disk only because Phase 1 has not yet landed.

```txt
skaal/
├── skaal/                  # Main Python package
│   ├── __init__.py         # Public API exports
│   ├── app.py              # `App` class (extends `Module`)
│   ├── module.py           # Core `Module` (composable units)
│   ├── agent.py            # (deletion pending — Phase 1) virtual actor base class
│   ├── api.py              # Python API (equivalents to CLI verbs)
│   ├── storage.py          # `Store[T, B]` typed container
│   ├── decorators.py       # `@app.storage`, `@app.function`, `@app.schedule`, `@app.job`, `@app.external`
│   ├── components.py       # (mostly deletion pending — Phase 1; `ExternalStorage`/`ExternalQueue` reshape into `@app.external` in Phase 2)
│   ├── patterns.py         # (deletion pending — Phase 1) `EventLog`, `Outbox`, `Projection`, `Saga`
│   ├── channel.py          # Cross-process messaging
│   ├── schedule.py         # `Cron`, `Every` scheduling primitives
│   ├── settings.py         # Unified config (env vars + pyproject.toml + `skaal.toml`)
│   ├── plan.py             # (deletion pending — Phase 1) `PlanFile` output structure; replaced by `InferredPlan`/`BoundPlan` in Phases 2–3
│   ├── types/              # Value types (`Duration`, `TTL`, `Page`, `SecondaryIndex`, …); constraint primitives are deletion pending — Phase 1
│   ├── backends/           # Backend implementations and typed `Backend` tokens (sqlite, redis, postgres, firestore, dynamodb, …)
│   ├── solver/             # (deletion pending — Phase 1) Z3 constraint solver
│   ├── inference/          # (Phase 2) walk `App` → `InferredPlan`
│   ├── binding/            # (Phase 3) bind `InferredPlan` + `Environment` + `LockFile` → `BoundPlan`
│   ├── runtime/            # Local execution engine (uvicorn + asyncio)
│   ├── deploy/             # Code generation for cloud targets (AWS, GCP, local)
│   │   └── templates/      # Jinja2 templates (Dockerfile, handler entrypoints, Pulumi programs)
│   ├── cli/                # CLI commands (typer)
│   ├── catalog/            # (deletion pending — Phase 1) TOML catalog loading
│   └── migrate/            # Schema migration engine (6-stage)
├── mesh/                   # (deletion pending — Phase 1) Rust PyO3 module
├── tests/                  # Pytest test suite (mirrors `skaal/` layout)
├── catalogs/               # (deletion pending — Phase 1) infrastructure catalogs
├── examples/               # Reference apps (counter, hello_world, todo_api, dash_app, …)
├── docs/                   # MkDocs site sources
│   └── design/             # Finalised Architecture Decision Records
├── notes/
│   ├── design/             # In-flight ADRs (028 redesign, 029 foundation, 030+ planned)
│   └── redesign-status.md  # Live progress tracker for the ADR 028 redesign
├── .github/                # CI/CD workflows and templates
└── README.md               # Project entry point
```

During the redesign, the layer map is:

- **Primitives layer** (`skaal.app`, `skaal.module`, `skaal.storage`, `skaal.blob`, `skaal.topic`, `skaal.table`, `skaal.decorators`): typed, structural primitives the user writes.
- **Inference layer** (`skaal.inference`, *Phase 2*): walks the `App` graph and produces an `InferredPlan` (pydantic, environment-independent).
- **Binding layer** (`skaal.binding`, *Phase 3*): binds an `InferredPlan` against an `Environment` and the `skaal.lock` file using a fixed defaults table — no search, no SMT.
- **Backend layer** (`skaal.backends`): concrete implementations registered via the in-tree backend registry; each is also a typed class token (`Postgres`, `BigQuery`, `Redis`, `DynamoDB`, …) usable as the second generic parameter on `Store[T, B]` / `Relational[T, B]` / etc.
- **Deploy layer** (`skaal.deploy`): Jinja2-driven code generation for Pulumi programs, Dockerfiles, and handler entrypoints — driven from the `BoundPlan`.
- **Runtime layer** (`skaal.runtime`): local execution engine built on Starlette + Uvicorn.

The constraint-era `skaal.solver` and `skaal.catalog` packages, the constraint primitives in `skaal.types`, and the `@app.handler` / `@app.scale` / `@app.shared` decorators were removed in Phase 1 (see ADR 029).

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
make test-storage                # storage tests only
make test-runtime                # runtime tests only
make test-schema                 # schema migration tests only

# Single test file
uv run --group test pytest tests/path/to/test_file.py
```

#### Key config files

- `pyproject.toml`: project metadata, dependencies, dependency groups, and tool configuration (ruff, mypy, pytest, coverage, bandit, hatch, skaal defaults).
- `uv.lock`: locked dependencies for reproducible builds.
- `Makefile`: development task entry points.
- `.pre-commit-config.yaml`: hooks executed on every commit.
- `notes/redesign-status.md`: live progress tracker for the ADR 028 redesign.
- `catalogs/*.toml`: legacy infrastructure catalogs consumed by the `0.3.x` solver. Scheduled for deletion in Phase 1 of the redesign (ADR 029).

#### PR and commit titles

Follow Conventional Commits. Keep titles short and descriptive — save detail for the body.

- Start the text after `type(scope):` with a lowercase letter, unless the first word is a proper noun (e.g. `AWS`, `GCP`, `Pulumi`) or a named entity (class, function, method, parameter, or variable name).
- Wrap named entities in backticks so they render as code. Proper nouns are left unadorned.
- Suggested scopes mirror the top-level subsystems: `inference`, `binding`, `runtime`, `deploy`, `backends`, `cli`, `migrate`, `types`, `docs`, `ci`. (`solver`, `catalog`, and `mesh` are scheduled for deletion in Phase 1 of the redesign and should not appear in new commit scopes.)

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

The redesign is intentionally breaking — ADR 028 commits to no backwards-compatibility shims for the `0.3.x` constraint vocabulary. *Within the redesign*, however, signature changes still need to be visible:

- Check whether the symbol is exported in `skaal/__init__.py` (the `__all__` list is authoritative).
- Look for existing usage patterns in `tests/`, `examples/`, and the surviving `docs/` pages.
- Use keyword-only arguments for new parameters: `*, new_param: str = "default"`.
- Mark experimental features clearly with docstring warnings (using MkDocs Material admonitions, like `!!! warning`).
- The new user-facing surface is `App`, `Module`, the typed primitives (`Store[T, B]`, `Relational[T, B]`, `BlobStore[B]`, `Channel[T, B]`), `@app.function`, `@app.schedule`, `@app.job`, and the `Backend` token tree under `skaal.backends`. Treat these as load-bearing once Phase 2 lands.

Ask: "Does this change need an entry in `notes/redesign-status.md`, or am I editing a surface a future phase will replace anyway?"

### Code quality standards

All Python code MUST include type hints and return types. The `skaal.types.*` module is subject to stricter `mypy` checks (`disallow_untyped_defs`, `warn_return_any`) per `pyproject.toml`. Phase 5 of the redesign extends `pyright --strict` to the whole `skaal/` tree.

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
- Coverage gate is `fail_under = 60` (see `[tool.coverage.report]`). Phase 1 of the redesign temporarily relaxes this to `40` while large surfaces are deleted; Phase 5 restores the floor.

**Checklist:**

- [ ] Tests fail when your new logic is broken
- [ ] Happy path is covered
- [ ] Edge cases and error conditions are tested
- [ ] Use fixtures/mocks for external dependencies (Redis, Postgres, S3, GCS)
- [ ] Tests are deterministic (no flaky tests)
- [ ] Inference- or binding-shape changes include a test asserting on the resulting `InferredPlan` or `BoundPlan`
- [ ] Backend changes are exercised through the contract suite in `tests/storage/`

### Security and risk assessment

Bandit runs in pre-commit at medium severity (`tests/`, `examples/`, and `skaal/deploy/templates/` are excluded).

- No `eval()`, `exec()`, or `pickle` on user-controlled input — `skaal.toml`, `skaal.lock`, and inference/binding artifacts are loaded via TOML/JSON, never `pickle`.
- Proper exception handling (no bare `except:`); use a `msg` variable when raising and let the CLI's Rich formatter render it.
- Remove unreachable/commented code before committing.
- Watch for race conditions or resource leaks in async code (file handles, sockets, connection pools, scheduler tasks).
- Ensure proper async cleanup — prefer `async with` for backends that own connections.
- Generated deployment artifacts (Pulumi programs, Dockerfiles) must not embed secrets — they should reference environment variables or the configured secrets backend.

### Documentation standards

Use Google-style docstrings with an `Args` section for all public functions.

```python title="Example"
def bind_resource(res: InferredResource, env: Environment, lock: LockFile) -> BoundResource:
    """Pick the concrete backend for a single inferred resource.

    The defaults table is only consulted for un-pinned resources; type-pinned
    classes (e.g. `Relational[Sale, BigQuery]`) bypass it entirely.

    Args:
        res: The inferred resource produced by the inference layer.
        env: The active environment loaded from `skaal.toml`.
        lock: The pin-on-first-deploy state loaded from `skaal.lock`.

    Returns:
        A `BoundResource` naming exactly one backend.

    Raises:
        TypePinViolation: If a type-pinned class is overridden to a different backend.
        BackendKindMismatch: If the chosen backend does not support the resource's required kinds.
    """
```

- Types go in function signatures, NOT in docstrings.
  - If a default is present, DO NOT repeat it in the docstring unless there is post-processing or it is set conditionally.
- Focus on "why" rather than "what" in descriptions.
- Document all parameters, return values, and exceptions.
- Keep descriptions concise but clear.
- Ensure American English spelling (e.g., "behavior", not "behaviour").
- Do NOT use Sphinx-style double backtick formatting (` ``code`` `). Use single backticks (`` `code` ``) for inline code references in docstrings and comments.
- ADRs in flight live under `notes/design/` as numbered Markdown files; once finalised they migrate to `docs/design/`. Reference them from PR descriptions when changing inference, binding, or generated artifact structure.

## Architecture and key patterns

The redesign's architecture is laid out in [ADR 028 §6](notes/design/028-code-first-infra-redesign.md). Until each phase lands, the canonical reference is the ADR itself rather than restating it here. Stable patterns:

### Resource declaration

Users declare typed primitives — `Store[T, B]`, `BlobStore[B]`, `Channel[T, B]`, `Relational[T, B]` — and functions decorated with `@app.function`, `@app.schedule`, or `@app.job`. The class **is** the resource; the second generic parameter (when supplied) is a typed `Backend` token that pins the binding. Decorator metadata is stored on the resource class as `__skaal_inferred__` (Phase 2) — never read these dunders directly from user code.

### Inference and binding pipeline

1. The user's `App` declares typed primitives and `@app.function` callables.
2. `skaal plan` walks the `App` graph and produces an `InferredPlan` (environment-independent, pydantic).
3. The binding layer combines the `InferredPlan` with the active `Environment` (from `skaal.toml`) and `skaal.lock` to produce a `BoundPlan` — pure table lookup, no search, no SMT.
4. `skaal build` generates Pulumi programs, Dockerfiles, and handler entrypoints from the `BoundPlan` via Jinja2 templates.
5. `skaal deploy` provisions infrastructure via Pulumi and pins the resulting bindings into `skaal.lock`.

### Storage abstractions

- `Store[T, B]` — typed key-value store (replaces `0.3.x` `Map[K, V]` and `Collection[T]`).
- `Relational[T, B]` — typed relational table (SQLModel + Alembic underneath).
- `BlobStore[B]` — object storage.
- `Channel[T, B]` — typed pub/sub.
- Backends are registered in the in-tree `skaal/binding/registry.py` (Phase 3). Each backend is also a typed class token (`from skaal.backends.bigquery import BigQuery`) usable as the second generic parameter on the primitives.

### Modules

- `Module` is the composable unit; `App` extends `Module`.
- Modules can include other modules via `app.include(module)`.

## Code conventions

- **Naming:** PascalCase for classes, snake_case for functions/variables.
- **Type hints:** used throughout; leverages `TypeVar`, `ParamSpec`, and generics. Stricter rules apply in `skaal.types.*`; Phase 5 extends `pyright --strict` to the whole tree.
- **Async-first:** prefer async functions for all I/O operations.
- **Imports:** organized by isort (enforced by Ruff `I` rule). First-party package: `skaal`.
- **Public API:** all public symbols are exported from `skaal/__init__.py` with explicit `__all__`.
- **Error handling:** standard Python exceptions; CLI wraps errors with Rich formatting.
- **Backend registry:** every backend is declared in `skaal/binding/registry.py` as a typed `Backend` subclass plus a `BackendEntry` record (Phase 3). No entry-point discovery; no TOML catalog overlay.
- **Settings:** `[tool.skaal]` in `pyproject.toml`, `skaal.toml` for environments, or `SKAAL_*` environment variables; CLI flags take precedence.

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
- Stricter overrides for `skaal.types.*`. Phase 5 of the redesign adds `pyright --strict` over the entire `skaal/` tree as a separate CI job.

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

When introducing a new storage or channel backend (Phase 3 onward):

- Add the implementation under `skaal/backends/<name>/`.
- Define the typed `Backend` token (subclass of `Backend[NativeClientT]`) so user code can pin to it via `Store[T, MyBackend]`.
- Add the backend's `BackendEntry` (token, `kinds`, `targets`, `capabilities`, `options_schema`) to the `REGISTRY` tuple in `skaal/binding/registry.py`.
- If the backend is the new default for a `(ResourceKind, Target)` slot, update `skaal/binding/defaults.py` *and* file an ADR justifying the change.
- Add a contract test under `tests/storage/` or `tests/backends/`.
- Document the backend's typed surface (kinds it supports, native client returned by `.native()`, env-config schema) in `docs/backends/<name>.md`.

## Key dependencies

| Package | Purpose |
|---------|---------|
| `pydantic` / `pydantic-settings` | Validation and settings; the entire inference and binding surface is pydantic. |
| `sqlmodel` / `alembic` | ORM and schema migrations |
| `typer` | CLI framework |
| `rich` | Terminal output formatting |
| `starlette` / `uvicorn` | Local web runtime (extra: `serve`) |
| `redis` | Redis backend |
| `aiosqlite` | SQLite async backend |
| `httpx` | HTTP client |
| `apscheduler` | Scheduling |
| `tenacity` / `pybreaker` | Retries and circuit breakers |
| `fsspec` | Filesystem abstractions |
| `pulumi` | Deployment automation (Automation API; users do not invoke `pulumi` directly) |

Optional extras: `aws` (`boto3`, `pulumi-aws`, `asyncpg`, `s3fs`); `gcp` (`google-cloud-*`, `pulumi-gcp`, `gcsfs`); `vector` (`langchain-*`, `chromadb`, `psycopg` — quarantined during the redesign); `fastapi`, `dash`, `secrets-aws`, `secrets-gcp`.

Removed during the redesign (Phase 1 of ADR 029): `z3-solver` (SMT solver), `langgraph` (agent orchestration), the `mesh` Rust crate / `maturin` build, and the catalog entry-point discovery layer.

## Working with this repo

- Always run `make lint` and `make test` before committing.
- Pre-commit hooks auto-fix formatting; if a commit is rejected, check the staged changes and retry.
- The `skaal/deploy/templates/` directory contains Jinja2 templates (not valid Python) — exclude from linting.
- Design decisions are documented as numbered ADRs in `notes/design/` (in flight) or `docs/design/` (finalised).
- During the redesign, every code change should also tick a checkbox in `notes/redesign-status.md` if it satisfies a phase exit criterion.
- Settings can be configured via `[tool.skaal]` in `pyproject.toml`, `skaal.toml`, or `SKAAL_*` environment variables.

## Additional resources

- **Documentation:** built with MkDocs Material; sources in `docs/`. Run `mkdocs serve` after `uv sync --group docs`.
- **Contributing Guide:** [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Citation:** see [`CITATION.cff`](CITATION.cff).
- **Issues:** https://github.com/Elouen-ginat/Skaal/issues
