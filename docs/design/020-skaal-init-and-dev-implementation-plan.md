# ADR 020 — `skaal init` and `skaal dev` Implementation Plan

**Status:** Proposed
**Date:** 2026-05-01
**Related:** [user_gaps.md §A.1](../user_gaps.md#a1-cli-zero-config-and-dev-loop), [skaal/cli/main.py](../../skaal/cli/main.py), [skaal/cli/run_cmd.py](../../skaal/cli/run_cmd.py), [skaal/settings.py](../../skaal/settings.py), [ADR 017](017-production-runtime-baseline-implementation-plan.md), [ADR 018](018-agent-persistence-implementation-plan.md)

## Goal

Make `pip install skaal && skaal init my-app && cd my-app && skaal dev` the documented first-run experience. The user gets a working app, a local catalog, a `pyproject.toml` already wired to `[tool.skaal]`, and a uvicorn process that reloads on save — without reading docs.

This pass closes user-gaps item **#3** ("`skaal init` / project scaffolding + `skaal dev` watch mode", §A.1) — the highest remaining adoption-blocking P0 after blob storage (ADR 016) and agent persistence (ADR 018) landed.

## Why this is next

The "Top of list" in `user_gaps.md` ranks items by reach × severity. Items #1 (blob tier — ADR 016) and #2 (agent persistence — ADR 018) are complete on `local`. The remaining P0s split into two buckets:

- **Adoption ergonomics** (#3 init/dev, #4 solver-error UX) — every new user hits these before any other gap.
- **Correctness/capability** (#6 relational migrations, #7 secrets, #10 per-row TTL) — only hit by users who already adopted Skaal.

Item #3 is a strict prerequisite for adoption-shaped work that follows. There is no point investing in #4's solver-error UX when the user can't get to a solve in the first place — `skaal init` is the entry point that makes `skaal plan` reachable. It is also the smallest scope of the P0s: ~two CLI commands, a Jinja2 template set, and a watcher loop.

The companion item from §A.1 — tab-completion install path — is in scope here because it is a one-line typer call and the `skaal init` template is the natural place to surface it.

## Scope

This pass includes:

- `skaal init <name>` command that creates a new project directory containing `pyproject.toml`, `app.py`, `catalogs/local.toml`, `.gitignore`, `README.md`, and a `tests/` skeleton.
- `--template <name>` flag with two starter templates: `kv` (a counter-style `Store[int]` app, mirrors `examples/01_hello_world`) and `crud` (a `Store[Model]` app with two functions, mirrors `examples/02_todo_api`). Default is `kv`.
- `--no-git` flag to skip `git init`. Default initializes a git repo with one commit.
- `skaal dev` command that resolves the app from `pyproject.toml`, starts uvicorn in `--reload` mode, and additionally watches the active catalog file(s); when the catalog changes, the runtime restarts (uvicorn's reloader does not natively watch non-Python paths).
- `skaal completion install [--shell bash|zsh|fish]` shim that writes the typer-generated completion to the conventional location and prints what it did.
- A short `docs/quickstart.md` page wired from the README.
- Tests covering: `skaal init` produces a project that `skaal plan` can solve and `skaal run` can serve; `skaal dev` reloads on `app.py` edit and on `catalogs/local.toml` edit; `--template crud` produces a project that responds to a CRUD round-trip.

This pass does **not** include:

- Cloud-target scaffolding (`skaal init --target gcp` writing GCP project IDs etc.). Init produces a target-agnostic `pyproject.toml`; cloud targets are still configured later.
- An interactive wizard. `skaal init` is non-interactive; flags only. Wizard mode is a future affordance once the flag set stabilizes.
- TUI, dashboard, or browser-launching for `skaal dev`. The reloader prints the URL and that is it.
- Agent / schedule / pattern templates. The `crud` template is the upper bound for this pass; richer ladders belong with the §A.8 examples work (separate plan).
- `skaal init` reading from a remote template registry. Templates are bundled in-tree under `skaal/cli/templates/`.

## Design

### `skaal init`

Module: `skaal/cli/init_cmd.py`. Registered as `app.add_typer(init_app, name="init")` in `skaal/cli/main.py`.

```
skaal init <name> [--template kv|crud] [--path .] [--no-git] [--force]
```

Behavior:

1. Resolve target dir: `Path(path) / name`. Reject if it exists and is non-empty unless `--force`.
2. Render the chosen template. Templates live at `skaal/cli/templates/<template_name>/` and are rendered through Jinja2 (already a transitive dep via `skaal/deploy/templates/`). Variables: `project_name`, `python_module` (`name` with `-`→`_`), `skaal_version` (read from `skaal.__version__`).
3. Write files. The set per template:
   - `pyproject.toml` — minimal `[project]` block, `dependencies = ["skaal[serve]"]`, `[tool.skaal] app = "<python_module>.app:app"`.
   - `<python_module>/__init__.py`, `<python_module>/app.py`.
   - `catalogs/local.toml` — copied from `skaal/catalogs/local.toml` (vendored at build time; see Files touched).
   - `tests/test_app.py` — uses the `LocalRuntime` test helper from §A.2 once it lands; for now, an `httpx.AsyncClient` round-trip against `serve_async`.
   - `.gitignore` — `__pycache__/`, `.skaal/`, `plan.skaal.lock`, `artifacts/`, `.skaal.env`.
   - `README.md` — three commands: `pip install -e .`, `skaal dev`, `curl localhost:8000/...`.
4. If `--no-git` is not set, run `git init`, `git add .`, `git commit -m "Initial Skaal project"`. Failure here logs a warning and continues — the project is still usable.
5. Print next-steps panel via `rich.panel.Panel` with the three commands.

The vendored `local.toml` shipped with `skaal init` is intentionally a thinned copy of the in-repo `catalogs/local.toml` — only the backends a fresh project will hit (`local-map`, `sqlite`, `local-redis`, `file-blob`). Cloud entries are omitted to keep the file scannable.

### `skaal dev`

Module: `skaal/cli/dev_cmd.py`. Registered as `app.add_typer(dev_app, name="dev")`.

```
skaal dev [MODULE:APP] [--host 127.0.0.1] [--port 8000] [--catalog catalogs/local.toml] [--no-reload]
```

Behavior is intentionally a thin wrapper over `skaal run` plus uvicorn's reload loop:

1. Resolve `MODULE:APP` via the same fallback chain as `run_cmd.py` (positional → `[tool.skaal] app`).
2. Resolve the catalog path via `SkaalSettings.catalog` with the same precedence; default `catalogs/local.toml`.
3. Start uvicorn programmatically with `reload=True`, `reload_dirs=[<project_root>]`, `reload_includes=["*.py"]`. uvicorn handles Python reload.
4. Spin a separate `watchfiles.awatch(<catalog_path>)` task that, on any event, calls `os.kill(os.getpid(), signal.SIGTERM)` so uvicorn's reloader picks up the change and restarts the worker. `watchfiles` is already a transitive uvicorn dep when `--reload` is used; no new top-level dep.
5. Refuse to start if `--persist` would be implied but the SQLite path is not writable — fail fast with a Skaal-shaped error, not a stack trace.
6. `--no-reload` falls through to `api.run(...)` — same path as `skaal run`. This makes `dev` safe to alias as the default command without losing the production-shaped path.

`skaal dev` does **not** add any auth, OTel, or middleware that `skaal run` does not already wire. It is the same runtime, with reload on.

### `skaal completion install`

Typer ships a `--install-completion` flag at the root callback. The friction is that users need to discover it and that the message it prints is generic. `skaal completion install` is a thin alias that:

1. Calls the underlying typer install routine.
2. Prints, via `rich`, the path written and the shell-restart instruction.

This is a pure UX shim — three lines of code, but it converts an undocumented affordance into a discoverable verb.

### Settings extension

`SkaalSettings` (`skaal/settings.py`) gains one optional field: `catalog: Path | None = None`. Resolution order matches existing fields (kwarg → env `SKAAL_CATALOG` → `[tool.skaal]` → default). This is consumed by `dev_cmd.py` and is backwards-compatible everywhere else (catalog discovery in `skaal/catalog/loader.py` already accepts an explicit path).

### Templates layout

```
skaal/cli/templates/
  kv/
    pyproject.toml.j2
    {{python_module}}/__init__.py.j2
    {{python_module}}/app.py.j2
    catalogs/local.toml          # not a template; copied verbatim
    tests/test_app.py.j2
    .gitignore                   # not a template
    README.md.j2
  crud/
    ... (same shape)
```

Templates are added to `pyproject.toml`'s `[tool.hatch.build.targets.wheel] include` list so they ship in the published wheel. The template loader uses `importlib.resources.files("skaal.cli.templates") / template_name` so it works from a wheel install without filesystem assumptions.

## Files touched

- `skaal/cli/main.py` — register `init_app` and `dev_app`; add the `completion` subcommand alias.
- `skaal/cli/init_cmd.py` (new) — implementation of `skaal init`.
- `skaal/cli/dev_cmd.py` (new) — implementation of `skaal dev`.
- `skaal/cli/templates/kv/...` (new tree) — kv starter template.
- `skaal/cli/templates/crud/...` (new tree) — crud starter template.
- `skaal/cli/_templates.py` (new) — shared Jinja2 environment + `render_template_dir(name, dst, ctx)` helper. Reused later by §A.8 example scaffolding work.
- `skaal/settings.py` — add `catalog: Path | None`.
- `pyproject.toml` — extend wheel `include` with `skaal/cli/templates/**/*`.
- `tests/cli/test_init_cmd.py` (new) — invokes `skaal init` into a `tmp_path`, asserts file set, runs `skaal plan` against the resulting project in a subprocess, and parses the lock file.
- `tests/cli/test_dev_cmd.py` (new) — starts `skaal dev` as a subprocess, performs a `curl` round-trip, edits `app.py`, asserts the new behavior is served. Marked `@pytest.mark.slow` because of process management.
- `docs/quickstart.md` (new short page) — three commands plus a one-paragraph "what just happened."
- `README.md` — replace the current install snippet with the three-command quickstart.

## Migration / compatibility

No breaking change. `skaal run` continues to exist and behave identically; `skaal dev` is purely additive. Existing `pyproject.toml` files are not rewritten by anything in this pass. The vendored `catalogs/local.toml` shipped with `skaal init` is independent of the in-repo copy used by Skaal's own examples — drift between them is acceptable because they serve different audiences (a fresh project vs. the framework's test harness).

The new `catalog` field on `SkaalSettings` is optional with `None` default; code paths that previously read it from elsewhere are untouched.

## Open questions

- **Where does `skaal init` write the catalog?** Two options: project root (`./catalogs/local.toml`) or a hidden `.skaal/catalogs/local.toml`. First cut uses project root because users edit it; the dotfile path can be opted into later if catalog inheritance (§A.5) lands and the base catalog should be hidden.
- **`skaal dev` and the mesh runtime.** Hot-reload of a Rust-backed mesh process is not free — restarting the mesh on every save is the conservative choice, but slow. Defer optimization until someone complains; mesh users typically don't run `dev`.
- **Template versioning.** Templates committed in-tree are pinned to the Skaal version that ships them. A `--template <name>@<version>` form would let users pull older shapes; out of scope until we have more than two templates and someone needs it.
- **`skaal init --here`.** A flag to scaffold into the current directory (instead of creating a child) is mildly useful but conflicts with `--force` in non-empty dirs. Punted unless it surfaces in user feedback.
- **Telemetry for first-run.** Whether `skaal init` should emit anonymous usage telemetry is a policy question separate from this plan; default is no telemetry until there is a documented privacy story.
