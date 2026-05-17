# What's new

This page tracks the current `0.4.0a0` documentation surface: what is here now, what is intentionally deferred, and how to think about the current alpha.

## In the current alpha

- Code-first primitives: `App`, `Module`, `Store`, `Table`, `BlobStore`, and `Topic`
- Named environments from `skaal.toml`
- Plan binding and lock pinning through `skaal.lock`
- Local runtime, mounted ASGI apps, and deploy rendering
- CLI commands for `run`, `plan`, `map`, `build`, `deploy`, `where`, `trace`, `stubs`, and `doctor`

## Deferred or still landing

- `skaal init` project scaffolding
- the public migration command group
- more CLI polish around environment and stack workflows
- broader GCP coverage and follow-up target work

## If you need the previous line

There is no migration path from `0.3.x` to the current line. If you need that release, pin `skaal==0.3.1`.

## How to read this docs set

- Start with [Get started](getting-started.md) for the local loop.
- Read [Concepts](concepts.md) and [How it works](how-it-works.md) for the model.
- Use [Examples](examples.md) and [CLI commands](cli.md) once you want complete flows.
